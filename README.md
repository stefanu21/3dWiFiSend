# 3dWiFiSend
Qidi X-Pro/X-Max Network Script

##### _note from original author:_
_This is a python script I threw together to allow me to send my gcode file from my pc to my printer over the network._

_The Qidi X-Pro 3D printer has network built in and allows you to send your files and start printing from Qidi's own software. I wanted to use Simplify 3D instead and also not have to walk to and from my printer so this script came out._

_I am not a python person. I absolutely hate python with a burning passion so this code is ugly and does not error-check. Basically, it is not written to really be distributed but I figured I'd share so that someone who actually has the patience to deal with python can improve it or whatever._

_I've tried to keep it simple to use._ 

###Instructions 

There are 2 files. 

One is the python script itself the other is a compressor for windows only - 
for macs you must have the QIDI Print software installed because it gets the compressor from there.
 
There is also a test file included, which is a small printer test file.

To use make sure that you have a flash drive plugged into the printer. I find it is a lot more reliable over ethernet than over wifi but YMMV. 

Here is how to use it:
"python qidi_connect.py [-p][-h] -i IPADDRESS -f FILE.GCODE"

example:

    python3 qidi_connect.py -p -i 192.168.3.100 -f test.gcode


note: Now works on mac and against QIDI X-MAX as well.


