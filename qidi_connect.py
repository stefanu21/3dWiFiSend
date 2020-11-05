import platform
import argparse
import time
from socket import *
import struct
import functools
from textwrap import dedent
import ipaddress
import subprocess
import os
from os import path


def send_receive(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        self = None
        for i in args:
            if isinstance(i, QidiConnect):
                self = i
                break

        if self is None:
            raise ValueError('no WifiDevice instance found')

        rx_buf_size = 256
        send = func(*args, **kwargs)
        if self.debug:
            print(f'send {send}')
        if isinstance(send, str):
            self.sock.sendto(bytes(send.encode('utf-8', 'ignore')), (self.host, self.port))
        else:
            self.sock.sendto(send, (self.host, self.port))

        if kwargs.get('no_recv', False):
            return

        msg = self.sock.recv(rx_buf_size)
        msg_len = len(msg)
        buf = msg
        while msg_len == rx_buf_size:
            msg = self.sock.recv(rx_buf_size)
            msg_len = len(msg)
            buf += msg

        if self.debug:
            print(f'receive {buf.decode("utf-8", "replace")}')

        return buf.decode('utf-8', 'replace')

    return wrap


class QidiConnect:
    _cmd_dict = {
        'printing_status': 'M27',
        'start_write_to_sd': 'M28',
        'end_write_to_sd': 'M29',
        'get_file_list': 'M20',
        'del_file_form_sd': 'M30',
        'current_position': 'M114',
        'device_info': 'M115',
        'm_status': 'M119',
        'bed_info': 'M4000',
        'step_parameter': 'M4001',
        'firmware': 'M4002',
        'off': 'M4003',
        'print': 'M6030',
        'temp_info': 'M105',
        'wifi_info': 'M99999',
    }

    # TODO: find this in the windows qidi software install and refer to it
    # TODO: also add platform.system() check like below
    # TODO: and remove the .exe from git
    VC_COMPRESS = ".\VC_compress_gcode.exe"
    if platform.system() == 'Darwin':  # for MacOS.  wish python had proper ternary operators....
        VC_COMPRESS = "/Applications/QIDI-Print.app//Contents/MacOS/VC_compress_gcode_MAC"

    def __init__(self, name, g_code_file, host, port=3000):
        self.debug = False
        self.host = host
        self.port = port
        self.name = name
        self.gcode_file = os.path.basename(g_code_file)
        self.gcode_dir = os.path.dirname(g_code_file)
        self.g_code_tar_file = None
        self.g_code_tar_dir = None
        self.e_mm_per_step = None
        self.z_mm_per_step = None
        self.y_mm_per_step = None
        self.x_mm_per_step = None

        self.s_machine_type = None
        self.s_x_max = None
        self.s_y_max = None
        self.s_z_max = None

        self.file_encode = None
        self.sock = None
        self.connect()

        self.init_machine_data()

    def disconnect(self):
        print('disconnect')
        if self.sock:
            self.sock.close()
            self.sock = None

    def connect(self):
        ip_addr = str(ipaddress.ip_address(self.host))
        self.disconnect()

        try:
            self.sock = socket(AF_INET, SOCK_DGRAM)
            self.sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
            self.sock.setblocking(0)
            self.sock.settimeout(5)
            print('connected')
        except socket.timeout as err:
            raise TimeoutError(err)

    def init_machine_data(self):
        bed_info = self.get_step_parameters()
        print(bed_info)
        if not any(i for i in bed_info if i in ('X', 'Y', 'Z')):
            raise ValueError('error get needed parameter from bed info')
        for i in ('\r', '\n'):
            bed_info = bed_info.replace(i, '')

        bed_info = bed_info.split(' ')
        for element in bed_info:
            item = element.split(':')
            if item[0] == 'X':
                self.x_mm_per_step = item[1]
            elif item[0] == 'Y':
                self.y_mm_per_step = item[1]
            elif item[0] == 'Z':
                self.z_mm_per_step = item[1]
            elif item[0] == 'E':
                self.e_mm_per_step = item[1]
            elif item[0] == 'T':
                self.s_machine_type, self.s_x_max, self.s_y_max, self.s_z_max, dummy = item[1].split('/')
            elif item[0] == 'U':
                self.file_encode = item[1].replace("'", "")

    def create_tar_file(self):
        cmd = path.normpath(QidiConnect.VC_COMPRESS) + f' "{self.gcode_dir}/{self.gcode_file}" ' \
              + " ".join((self.x_mm_per_step, self.y_mm_per_step, self.z_mm_per_step, self.e_mm_per_step)) \
              + f' "{self.gcode_dir}" ' \
              + ' '.join((self.s_x_max, self.s_y_max, self.s_z_max, self.s_machine_type))

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
        try:
            outs, err = proc.communicate(timeout=10)
            outs = outs.decode('utf-8').splitlines()
            print(outs)
            output_file = [x for x in outs if 'open output file' in x][0]
            output_file = output_file[len('open output file '):].split(' ')[0]
            self.g_code_tar_file = os.path.basename(output_file)
            self.g_code_tar_dir = os.path.dirname(output_file)

        except subprocess.TimeoutExpired:
            proc.kill()
            outs, errs = proc.communicate()
            raise ValueError(f'error create tar file {errs}')

    @send_receive
    def start_write_to_sd_cmd(*args, **kwargs):
        return QidiConnect._cmd_dict['start_write_to_sd'] + ' ' + args[0].g_code_tar_file

    @send_receive
    def end_write_to_sd_cmd(*args, **kwargs):
        return QidiConnect._cmd_dict['end_write_to_sd'] + ' ' + args[0].g_code_tar_file

    @send_receive
    def send_file_chunk(*args, **kwargs):
        data_array = bytearray(kwargs['data_chunk'])
        data_len = len(data_array)

        if data_len == 0:
            raise ValueError('data size is zero')

        seek_array = struct.pack('<I', kwargs['seek_pos'])
        data_array += bytearray(seek_array)

        check_sum = 0
        for i in range(0, data_len + len(seek_array), 1):
            check_sum ^= data_array[i]

        data_array += bytearray(b'00')
        data_array[-2] = check_sum
        data_array[-1] = 0x83

        return data_array

    @send_receive
    def sendFileChunk(*args, **kwargs):
        data = args[0].addCheckSum(kwargs['buff'], kwargs['seekPos'])
        if len(data) - 6 <= 0:
            raise ValueError('data size is zero')

        return data

    def sendFile(self):
        print(f'start write to sd {self.start_write_to_sd_cmd()}')
        # TODO fix time wait
        time.sleep(3)
        with open(self.g_code_tar_dir + '/' + self.g_code_tar_file, 'rb', buffering=1) as fp:
            while True:
                seek_pos = fp.tell()
                chunk = fp.read(1024)
                if not chunk:
                    break
                self.send_file_chunk(data_chunk=chunk, seek_pos=seek_pos, no_recv=False)

        print(f'end write to sd - {self.end_write_to_sd_cmd()}')

    @send_receive
    def start_print(*args, **kwargs):
        return QuidiConnect._cmd_dict['print'] + '":' + args[0].g_code_tar_file + '" I1'

    @send_receive
    def get_device_info(*args, **kwargs):
        return QidiConnect._cmd_dict['device_info']

    @send_receive
    def get_firmware_info(*args, **kwargs):
        return QidiConnect._cmd_dict['firmware']

    @send_receive
    def get_step_parameters(*args, **kwargs):
        return QidiConnect._cmd_dict['step_parameter']

    @send_receive
    def get_bed_info(*args, **kwargs):
        return QidiConnect._cmd_dict['bed_info']

    @send_receive
    def get_temp_info(*args, **kwargs):
        return QidiConnect._cmd_dict['temp_info']

    @send_receive
    def get_wifi_info(*args, **kwargs):
        return QidiConnect._cmd_dict['wifi_info']


def main():
    """Main program
    """
    description = """Simple programm to send commands to Qidi Printers
    """
    parser = argparse.ArgumentParser(description=dedent(description))
    parser.add_argument('-i',
                        '--IPv4',
                        action='store',
                        dest='host',
                        help='ip address (ipv4)')
    parser.add_argument('-n',
                        '--name',
                        action='store',
                        dest='name',
                        help='3d printer name')
    parser.add_argument('-f',
                        action='store',
                        dest='g_code_file',
                        help='g-code file location')
    parser.add_argument('-p',
                        '--print',
                        action='store_true',
                        help='print file')

    args = parser.parse_args()

    dev = QidiConnect(args.name, args.g_code_file, args.host)
    dev.create_tar_file()
    dev.sendFile()

    if args.print:
        dev.start_print()


if __name__ == '__main__':
    main()
