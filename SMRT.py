# Copyright 2015 Yahoo! Inc.
# Licensed under the GPL 3.0 license.  Developed for Yahoo! by Sean Gillespie.
#
# Yahoo! licenses this file to you under the GPL License, Version
# 3 (the "License"); you may not use this file except in compliance with the
# License.  You may obtain a copy of the License at:
#
#        http://www.gnu.org/licenses/gpl-3.0.html
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.  See the License for the specific language governing
# permissions and limitations under the License.

import sublime
import sublime_plugin
import io
import gzip
import base64
import hashlib
import time
import re
import binascii
import zlib
import urllib.parse
import socket
import struct
from SMRT.pescanner import pescanner


def ParseHex(hextext):
    if re.search(r'^([xX][0-9A-F]{2})+$', hextext):
        hextext = re.sub(r'x', '', hextext)
    else:
        hextext = re.sub(r'(0[xX]|\\[xX]|\\[uU]|%[uU]|%|\s)',
                         '', hextext).upper()

    if re.search('^[0-9A-F]+$', hextext):
        if len(hextext) % 2 != 0:
            hextext = "0" + hextext
        return hextext
    else:
        return None


def FormatHex(hextext, bytes=1, newlines=True):
    step = bytes * 2
    formathex = ""

    if not re.search('^[0-9A-F]+$', hextext):
        hextext = ParseHex(hextext)

    if hextext is not None:
        for i in range(0, len(hextext), step):
            formathex += hextext[i:i+step]
            if len(hextext[:i+step]) % 32 == 0 and newlines:
                formathex += "\n"
            else:
                formathex += " "

        return formathex.upper().rstrip()
    else:
        return None


def XorData(hextext, xor, skip_zero_and_key):
    xorlen = len(xor)
    xorbyte = int(xor, 16)
    xortext = ''
    chunks, chunk_size = len(hextext), xorlen
    bytearray = [hextext[i:i+chunk_size] for i in range(0, chunks, chunk_size)]
    for bytechunk in bytearray:
        if skip_zero_and_key:
            if int(bytechunk, 16) == xorbyte or int(bytechunk, 16) == 0:
                xortext += bytechunk.lower()
            else:
                xortext += "{0:0{1}x}".format((int(bytechunk, 16) ^ xorbyte), len(bytechunk))
        else:
            xortext += "{0:0{1}x}".format((int(bytechunk, 16) ^ xorbyte), len(bytechunk))
    return xortext


class SwitchEndiannessCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        for sel in self.view.sel():
            if not sel.empty():
                hextext = ParseHex(self.view.substr(sel))
                if hextext is not None:
                    bytearray = [hextext[i:i+2] for i in range(0, len(hextext), 2)]
                    bytearray.reverse()
                    hextext = "".join(bytearray)
                    self.view.replace(edit, sel, hextext)
                else:
                    self.view.replace(edit, sel, "*Non-hex Input: \\xFF\\xFF xFFxFF %FF%FF \\uFFFF %uFFFF FFFF 0xFFFF expected*")


class IntToIpCommand(sublime_plugin.TextCommand):
    def run(self, edit, order):
        for sel in self.view.sel():
            if not sel.empty():
                inttext = self.view.substr(sel)
                if re.search('^[0-9]+$', inttext):
                    if order == "N":
                        ip = socket.inet_ntoa(struct.pack('>L', int(inttext)))
                    if order == "H":
                        ip = socket.inet_ntoa(struct.pack('<L', int(inttext)))
                    self.view.replace(edit, sel, ip)
                else:
                    self.view.replace(edit, sel, "*Non-integer Input*")


class IpToIntCommand(sublime_plugin.TextCommand):
    def run(self, edit, order):
        for sel in self.view.sel():
            if not sel.empty():
                iptext = self.view.substr(sel)
                if re.search('^((([01]{0,1}[0-9]{1,2})|(2[0-5]{2}))\.){3}(([01]{0,1}[0-9]{1,2})|(2[0-5]{2}))$', iptext):
                    if order == "N":
                        ipint = struct.unpack(">L", socket.inet_aton(iptext))[0]
                    if order == "H":
                        ipint = struct.unpack("<L", socket.inet_aton(iptext))[0]
                    inttext = str(ipint)
                    self.view.replace(edit, sel, inttext)
                else:
                    self.view.replace(edit, sel, "*Non-IPv4 Input*")


class UrlUnquoteCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        for sel in self.view.sel():
            if not sel.empty():
                urltext = self.view.substr(sel)
                urltext = urllib.parse.unquote(urltext)
                self.view.replace(edit, sel, urltext)


class UrlQuoteCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        for sel in self.view.sel():
            if not sel.empty():
                urltext = self.view.substr(sel)
                urltext = urllib.parse.quote(urltext)
                self.view.replace(edit, sel, urltext)


class CompressCommand(sublime_plugin.TextCommand):
    def run(self, edit, cformat='zlib'):
        for sel in self.view.sel():
            if not sel.empty():
                hextext = ParseHex(self.view.substr(sel))
                if hextext is not None:
                    ddata = binascii.unhexlify(hextext)
                    if cformat == 'zlib':
                        cdata = zlib.compress(ddata)
                    if cformat == 'deflate':
                        cdata = zlib.compress(ddata)[2:-4]
                    if cformat == 'gzip':
                        gzip_out = io.BytesIO()
                        with gzip.GzipFile(fileobj=gzip_out, mode='w') as fd:
                            fd.write(ddata)
                        cdata = gzip_out.getvalue()
                    hextext = binascii.hexlify(cdata)
                    formathex = FormatHex(hextext.decode('utf-8'))
                    self.view.replace(edit, sel, formathex)
                else:
                    self.view.replace(edit, sel, "*Non-hex Input: \\xFF\\xFF xFFxFF %FF%FF \\uFFFF %uFFFF FFFF 0xFFFF expected*")


class ZlibDecompressCommand(sublime_plugin.TextCommand):
    def run(self, edit, wbits=15):
        for sel in self.view.sel():
            if not sel.empty():
                hextext = ParseHex(self.view.substr(sel))
                if hextext is not None:
                    cdata = binascii.unhexlify(hextext)
                    ddata = zlib.decompress(cdata, wbits)
                    hextext = binascii.hexlify(ddata)
                    formathex = FormatHex(hextext.decode('utf-8'))
                    self.view.replace(edit, sel, formathex)
                else:
                    self.view.replace(edit, sel, "*Non-hex Input: \\xFF\\xFF xFFxFF %FF%FF \\uFFFF %uFFFF FFFF 0xFFFF expected*")


class HexEncodeCommand(sublime_plugin.TextCommand):
    def run(self, edit, encoding="ascii"):
        for sel in self.view.sel():
            if not sel.empty():
                text = self.view.substr(sel).encode(encoding)
                hextext = binascii.hexlify(text)
                formathex = FormatHex(hextext.decode('utf-8'))
                self.view.replace(edit, sel, formathex)


class HexDecodeCommand(sublime_plugin.TextCommand):
    def run(self, edit, encoding="ascii"):
        for sel in self.view.sel():
            if not sel.empty():
                hextext = ParseHex(self.view.substr(sel))
                if hextext is not None:
                    text = binascii.unhexlify(hextext).decode(encoding)
                    cleantext = re.sub(r'[\t\n\r]', '.', text)
                    self.view.replace(edit, sel, cleantext)
                else:
                    self.view.replace(edit, sel, "*Non-hex Input: \\xFF\\xFF xFFxFF %FF%FF \\uFFFF %uFFFF FFFF 0xFFFF expected*")


class FormatHexCommand(sublime_plugin.TextCommand):
    def run (self, edit, bytes):
        for sel in self.view.sel():
            if not sel.empty():
                hextext = ParseHex(self.view.substr(sel))
                if hextext is not None:
                    formathex = FormatHex(hextext, bytes)
                    self.view.replace(edit, sel, formathex)
                else:
                    self.view.replace(edit, sel, "*Non-hex Input: \\xFF\\xFF xFFxFF %FF%FF \\uFFFF %uFFFF FFFF 0xFFFF expected*")


class BaseXxEncodeCommand(sublime_plugin.TextCommand):
    def run(self, edit, xx=64, table=None):
        for sel in self.view.sel():
            if not sel.empty():
                text = self.view.substr(sel).encode('utf-8')
                bxxtext = "*No Encoding Selected*"
                if xx == 64:
                    bxxtext = base64.b64encode(text)
                if xx == 32:
                    bxxtext = base64.b32encode(text)
                self.view.replace(edit, sel, bxxtext.decode('utf-8'))


class BaseXxDecodeCommand(sublime_plugin.TextCommand):
    def run(self, edit, xx=64, table=None):
        for sel in self.view.sel():
            if not sel.empty():
                bxxtext = self.view.substr(sel)
                text = "*Improper or No Decoding Selected*"
                if xx == 64 and re.search('^[A-Za-z0-9+/=]+$', bxxtext):
                    if len(bxxtext) % 4 != 0:
                        bxxtext += "=" * (4 - (len(bxxtext) % 4))
                    text = base64.b64decode(bxxtext.encode('utf-8'))
                if xx == 32 and re.search('^[A-Z2-7=]+$', bxxtext):
                    if len(bxxtext) % 8 != 0:
                        bxxtext += "=" * (8 - (len(bxxtext) % 8))
                    text = base64.b32decode(bxxtext.encode('utf-8'))
                self.view.replace(edit, sel, text.decode('utf-8'))


class BaseXxEncodeBinaryCommand(sublime_plugin.TextCommand):
    def run(self, edit, xx=64, table=None):
        for sel in self.view.sel():
            if not sel.empty():
                hextext = ParseHex(self.view.substr(sel))
                data = binascii.unhexlify(hextext)
                bxxtext = "*No Encoding Selected*"
                if xx == 64:
                    bxxtext = binascii.b2a_base64(data)
                self.view.replace(edit, sel, bxxtext.decode('utf-8'))


class BaseXxDecodeBinaryCommand(sublime_plugin.TextCommand):
    def run(self, edit, xx=64, table=None):
        for sel in self.view.sel():
            if not sel.empty():
                # TODO Regex for charset and check/correct padding if necessary
                bxxtext = self.view.substr(sel)
                formathex = "*No Decoding Selected*"
                if xx == 64:
                    data = binascii.a2b_base64(bxxtext)
                    print(data)
                    hextext = binascii.hexlify(data)
                    formathex = FormatHex(hextext.decode('utf-8'))
                self.view.replace(edit, sel, formathex)


class TextTranslateCommand(sublime_plugin.TextCommand):
    def run(self, edit, rot, transin="AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz"):
        transout = transin[rot:] + transin[:rot]
        rottrans = str.maketrans(transin, transout)
        for sel in self.view.sel():
            if not sel.empty():
                text = self.view.substr(sel)
                rottext = str(text).translate(rottrans)
                self.view.replace(edit, sel, rottext)


class HashCommand(sublime_plugin.TextCommand):
    def run(self, edit, alg=None):
        for sel in self.view.sel():
            hashtext = self.view.substr(sel).encode('utf-8')
            if alg == "md5":
                hashed = hashlib.md5(hashtext).hexdigest()
            elif alg == "sha1":
                hashed = hashlib.sha1(hashtext).hexdigest()
            elif alg == "sha256":
                hashed = hashlib.sha256(hashtext).hexdigest()
            else:
                hashed = "*No algorithm selected*"
            self.view.replace(edit, sel, hashed)


class TimestampFromIntCommand(sublime_plugin.TextCommand):
    def run(self, edit, format="Unix"):
        for sel in self.view.sel():
            if not sel.empty():
                timeint = self.view.substr(sel)
                timetext = "*No Timestamp Format Selected*"
                if format == "Unix":
                    timetext = time.strftime("%d-%b-%Y %H:%M:%S", time.gmtime(int(timeint)))
                self.view.replace(edit, sel, timetext)


class IntToHexCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        for sel in self.view.sel():
            if not sel.empty():
                inttext = self.view.substr(sel)
                if re.search('^[0-9]+$', inttext):
                    hextext = FormatHex("%x" % (int(inttext)))
                    self.view.replace(edit, sel, hextext)
                else:
                    self.view.replace(edit, sel, "*Non-integer Input*")


class HexToIntCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        for sel in self.view.sel():
            if not sel.empty():
                hextext = ParseHex(self.view.substr(sel))
                if hextext is not None:
                    text = str(int(hextext, 16))
                    self.view.replace(edit, sel, text)
                else:
                    self.view.replace(edit, sel, "*Non-hex Input: \\xFF\\xFF xFFxFF %FF%FF \\uFFFF %uFFFF FFFF 0xFFFF expected*")


class PeScannerCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        peid_sigs = sublime.packages_path() + '/SMRT/peid.db'
        for sel in self.view.sel():
            hextext = ParseHex(self.view.substr(sel))
            if hextext is not None:
                pehex = pescanner.PEScanner(binascii.unhexlify(hextext), peid_sigs=peid_sigs)
                report_file = self.view.window().new_file()
                report_file.set_name("PE Scanner Report")
                report_file.insert(edit, 0, '\n'.join(pehex.collect()))


class GetTextRotValue(sublime_plugin.WindowCommand):
    def run(self):
        self.window.show_input_panel('Rotation', '', self.on_done, None, None)

    def on_done(self, rot):
        if re.search('^[0-9]+$', rot):
            rot = int(rot)
            if self.window.active_view():
                self.window.active_view().run_command("text_translate", {"rot": rot*2})
        else:
            if self.window.active_view():
                self.window.active_view().run_command("display_input_error", {"errortext": "*Non-integer Input*"})


class GetSwapMap(sublime_plugin.WindowCommand):
    def run(self):
        self.window.show_input_panel('Swap Map', '', self.on_done, None, None)

    def on_done(self, swapmap):
        if re.search('[^:]+:[^:]+', swapmap):
            seta, setb = swapmap.split(":")
            if len(seta) == len(setb):
                rot = len(seta)
                transin = seta + setb
                if self.window.active_view():
                    self.window.active_view().run_command("text_translate", {"rot": rot, "transin": transin})
            else:
                if self.window.active_view():
                    self.window.active_view().run_command("display_input_error", {"errortext": "*Invalid Swap Map: Use Xx:Yy format*"})
        else:
            if self.window.active_view():
                self.window.active_view().run_command("display_input_error", {"errortext": "*Invalid Swap Map: Use Xx:Yy format*"})


class ApplyXorCommand(sublime_plugin.TextCommand):
    def run(self, edit, xor, skip_zero_and_key):
        for sel in self.view.sel():
            if not sel.empty():
                hextext = ParseHex(self.view.substr(sel))
                if hextext is not None and (len(hextext) % len(xor) == 0):
                    xor_hextext = XorData(hextext, xor, skip_zero_and_key)
                    formathex = FormatHex(xor_hextext)
                    self.view.replace(edit, sel, formathex)
                else:
                    self.view.replace(edit, sel, "*Invalid Hex Data or Length*")


class ApplyXorRangeCommand(sublime_plugin.TextCommand):
    def run(self, edit, xor_range, skip_zero_and_key):
        first_byte, last_byte = xor_range.split("-")
        if len(first_byte) == len(last_byte):
            first = int(first_byte, 16)
            last = int(last_byte, 16)
            if first < last:
                byte_range = range(first, last)
            else:
                byte_range = range(last, first)

            output = ''
            for sel in self.view.sel():
                if not sel.empty():
                    hextext = ParseHex(self.view.substr(sel))
                    if hextext is not None and (len(hextext) % len(first_byte) == 0):
                        for byte in byte_range:
                            xor = "%X" % byte
                            xor = xor.zfill(len(first_byte))
                            xor_hextext = XorData(hextext, xor, skip_zero_and_key)
                            formathex = FormatHex(xor_hextext, newlines=False)
                            text = re.sub(r'(\\x[a-f0-9]{2}|\\t|\\r|\\n)', '.', str(binascii.unhexlify(xor_hextext)).rstrip().lstrip())[2:-1]
                            output += xor + ":\t\t" + formathex + "\t\t" + text + "\n"
                        outputfile = self.view.window().new_file()
                        outputfile.set_name("XOR Range: " + first_byte + "-" + last_byte)
                        outputfile.insert(edit, 0, output)
                    else:
                        self.view.replace(edit, sel, "*Invalid Hex Data or Length*")
        else:
            self.view.replace(edit, sel, "*Start and End byte length mismatch*")


class GetXorKeys(sublime_plugin.WindowCommand):
    def run(self, skip_zero_and_key=False):
        self.skip_zero_and_key = skip_zero_and_key
        self.window.show_input_panel('XOR Bytes', '', self.on_done, None, None)

    def on_done(self, xor):
        try:
            if re.search('^([A-F0-9]{2})+$', xor.upper()):
                if self.window.active_view():
                    self.window.active_view().run_command("apply_xor", {"xor": xor, "skip_zero_and_key": self.skip_zero_and_key})
            elif re.search('^([A-F0-9]{2})+-([A-F0-9]{2})+$', xor.upper()):
                if self.window.active_view():
                    self.window.active_view().run_command("apply_xor_range", {"xor_range": xor, "skip_zero_and_key": self.skip_zero_and_key})
        except ValueError:
            pass
