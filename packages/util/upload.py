# -*- coding: utf-8 -*-
'''
Parser for multipart/form-data
==============================

This module provides a parser for the multipart/form-data format. It can read
from a file, a socket or a WSGI environment. The parser can be used to replace
cgi.FieldStorage (without the bugs) and works with Python 2.6+ and 3.x
(single-source).

Licence (MIT)
-------------

    Copyright (c) 2010, Marcel Hellkamp.
    Inspired by the Werkzeug library: http://werkzeug.pocoo.org/

    Permission is hereby granted, free of charge, to any person obtaining
    a copy of this software and associated documentation files (the
    "Software"), to deal in the Software without restriction, including without
    limitation the rights to use, copy, modify, merge, publish, distribute,
    sublicense, and/or sell copies of the Software, and to permit persons to
    whom the Software is furnished to do so, subject to the following
    conditions:

    The above copyright notice and this permission notice shall be included in
    all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
    DEALINGS IN THE SOFTWARE.

'''

__author__ = 'Marcel Hellkamp'
__version__ = '0.1'
__license__ = 'MIT'

from tempfile import TemporaryFile
from wsgiref.headers import Headers
import re
import binascii
import quopri
try:
    from urlparse import parse_qs
except ImportError:  # pragma: no cover (fallback for Python 2.x)
    from cgi import parse_qs
try:
    from io import BytesIO
except ImportError:  # pragma: no cover (fallback for Python 2.x)
    from StringIO import StringIO as BytesIO
try:
    unicode
except NameError:
    unicode = str

##############################################################################
################################ Helper & Misc ################################
##############################################################################
# Some of these were copied from bottle: http://bottle.paws.de/

try:
    from collections import MutableMapping as DictMixin
except ImportError:  # pragma: no cover (fallback for Python 2.x)
    from UserDict import DictMixin
from sys import version_info


def item_iterator(some_dict):
    "Wrapper to get an iterator over items in Python 2 or 3"
    if version_info >= (3, 0):
        return some_dict.items()
    return some_dict.iteritems()


class MultiDict(DictMixin):
    """ A dict that remembers old values for each key """
    def __init__(self, *a, **k):
        self.dict = dict()
        for k, v in item_iterator(dict(*a, **k)):
            self[k] = v

    def __len__(self):
        return len(self.dict)

    def __iter__(self):
        return iter(self.dict)

    def __contains__(self, key):
        return key in self.dict

    def __delitem__(self, key):
        del self.dict[key]

    def keys(self):
        return self.dict.keys()

    def __getitem__(self, key):
        return self.get(key, KeyError, -1)

    def __setitem__(self, key, value):
        self.append(key, value)

    def append(self, key, value):
        self.dict.setdefault(key, []).append(value)

    def replace(self, key, value):
        self.dict[key] = [value]

    def getall(self, key):
        return self.dict.get(key) or []

    def get(self, key, default=None, index=-1):
        if key not in self.dict and default != KeyError:
            return [default][index]
        return self.dict[key][index]

    def iterallitems(self):
        for key, values in item_iterator(self.dict):
            for value in values:
                yield key, value


def tob(data, enc='utf8'):  # Convert strings to bytes (py2 and py3)
    return data.encode(enc) if isinstance(data, unicode) else data


def copy_file(stream, target, maxread=-1, buffer_size=2 * 16):
    ''' Read from :stream and write to :target until :maxread or EOF. '''
    size, read = 0, stream.read
    while 1:
        to_read = buffer_size if maxread < 0 \
                              else min(buffer_size, maxread - size)
        part = read(to_read)
        if not part:
            return size
        target.write(part)
        size += len(part)


def lineiter(stream, limit=2 ^ 13, readlimit=-1):
    ''' Read from a binary stream and yield (line, terminator) tuples. The
        stream object must implement a `read(bytes)` method.

        All common line terminators are recognized (NL, CR and CRNL). CR is
        only considered if it is not followed by a NL. Lines that exceed a size
        of `limit` bytes (excluding terminator) are split into chunks of
        `limit` bytes. The terminator is an empty byte string for all but the
        last chunk of a line. If `readlimit` is set, no more than `readlimit`
        bytes are read from the stream. At no time more than (limit+2)*2 bytes
        are buffered in memory.
    '''
    read = stream.read
    crnl = tob('\r\n')  # Python 3 hack (be sure to get bytes and not unicode)
    cr, nl, empty = crnl[:1], crnl[1:], crnl[:0]
    cache = empty  # buffer for the last (partial) line
    while 1:
        # Read chunk so that cache+chunk fits into $limit+2 bytes
        memlimit = limit - len(cache) + 2
        chunk = read(memlimit if readlimit < 0 else min(readlimit, memlimit))
        readlimit -= len(chunk)
        # Split lines.
        lines = (cache + chunk).splitlines(True)
        cache = lines.pop() if chunk else empty
        if len(cache) >= limit:
            split = limit if cache[limit] != cr else limit - 1
            lines.append(cache[:split])
            cache = cache[split:]
        for line in lines:
            if line.endswith(crnl):
                yield line[:-2], crnl
            elif line.endswith(nl):
                yield line[:-1], nl
            elif line.endswith(cr):
                yield line[:-1], cr
            else:
                yield line, empty
        if not chunk:
            break

##############################################################################
################################ Header Parser ################################
##############################################################################

_special = re.escape('()<>@,;:\\"/[]?={} \t')
_re_special = re.compile('[%s]' % _special)
_qstr = '"(?:\\\\.|[^"])*"'  # Quoted string
_value = '(?:[^%s]+|%s)' % (_special, _qstr)  # Save or quoted string
_option = '(?:;|^)\s*([^%s]+)\s*=\s*(%s)' % (_special, _value)
_re_option = re.compile(_option)  # key=value part of Content-Type like header


def header_quote(val):
    if not _re_special.search(val):
        return val
    return '"' + val.replace('\\', '\\\\').replace('"', '\\"') + '"'


def header_unquote(val, filename=False):
    if val[0] == val[-1] == '"':
        val = val[1:-1]
        if val[1:3] == ':\\' or val[:2] == '\\\\':
            val = val.split('\\')[-1]  # fix IE6 bug: full path --> filename
        return val.replace('\\\\', '\\').replace('\\"', '"')
    return val


def parse_options_header(header, options=None):
    if ';' not in header:
        return header.lower().strip(), {}
    ctype, tail = header.split(';', 1)
    options = options or {}
    for match in _re_option.finditer(tail):
        key = match.group(1).lower()
        value = header_unquote(match.group(2), key == 'filename')
        options[key] = value
    return ctype, options

##############################################################################
################################## Multipart ##################################
##############################################################################


class MultipartError(ValueError):
    pass


class MultipartParser(object):

    def __init__(self, stream, boundary, content_length=-1,
                 disk_limit=2 ** 30, mem_limit=2 ** 20, memfile_limit=2 ** 18,
                 buffer_size=2 ** 16, charset='latin1'):
        ''' Parse a multipart/form-data byte stream. This object is an iterator
            over the parts of the message.

            :param stream: A file-like stream. Must implement ``.read(size)``.
            :param boundary: The multipart boundary as a byte string.
            :param content_length: The maximum number of bytes to read.
        '''
        self.stream, self.boundary = stream, boundary
        self.content_length = content_length
        self.disk_limit = disk_limit
        self.memfile_limit = memfile_limit
        self.mem_limit = min(mem_limit, self.disk_limit)
        self.buffer_size = min(buffer_size, self.mem_limit)
        self.charset = charset
        if self.buffer_size - 6 < len(boundary):  # "--boundary--\r\n"
            raise MultipartError('Boundary does not fit into buffer_size.')
        self._done = []
        self._part_iter = None

    def __iter__(self):
        ''' Iterate over the parts of the multipart message. '''
        if not self._part_iter:
            self._part_iter = self._iterparse()
        for part in self._done:
            yield part
        for part in self._part_iter:
            self._done.append(part)
            yield part

    def parts(self):
        ''' Returns a list with all parts of the multipart message. '''
        return list(iter(self))

    def get(self, name, default=None):
        ''' Return the first part with that name or a default value (None). '''
        for part in self:
            if name == part.name:
                return part
        return default

    def get_all(self, name):
        ''' Return a list of parts with that name. '''
        return [p for p in self if p.name == name]

    def _iterparse(self):
        lines = lineiter(self.stream, self.buffer_size, self.content_length)
        line = ''
        separator = tob('--') + tob(self.boundary)
        terminator = tob('--') + tob(self.boundary) + tob('--')
        # Consume first boundary. Ignore leading blank lines
        for line, nl in lines:
            if line:
                break
        if line != separator:
            raise MultipartError("Stream does not start with boundary")
        # For each part in stream...
        mem_used, disk_used = 0, 0  # Track used resources to prevent DoS
        is_tail = False  # True if the last line was incomplete (cut)
        opts = {'buffer_size': self.buffer_size,
                'memfile_limit': self.memfile_limit,
                'charset': self.charset}
        part = MultipartPart(**opts)
        for line, nl in lines:
            if line == terminator and not is_tail:
                part.file.seek(0)
                yield part
                break
            elif line == separator and not is_tail:
                if part.is_buffered():
                    mem_used += part.size
                else:
                    disk_used += part.size
                part.file.seek(0)
                yield part
                part = MultipartPart(**opts)
            else:
                is_tail = not nl  # The next line continues this one
                part.feed(line, nl)
                if part.is_buffered():
                    if part.size + mem_used > self.mem_limit:
                        raise MultipartError("Memory limit reached.")
                elif part.size + disk_used > self.disk_limit:
                    raise MultipartError("Disk limit reached.")
        if line != terminator:
            raise MultipartError("Unexpected end of multipart stream.")


class MultipartPart(object):

    def __init__(self, buffer_size=2 ** 16, memfile_limit=2 ** 18,
                 charset='latin1'):
        self.headerlist = []
        self.headers = None
        self.file = False
        self.size = 0
        self._buf = tob('')
        self.disposition, self.name, self.filename = None, None, None
        self.content_type, self.charset = None, charset
        self.memfile_limit = memfile_limit
        self.buffer_size = buffer_size

    def feed(self, line, nl=''):
        if self.file:
            return self.write_body(line, nl)
        return self.write_header(line, nl)

    def write_header(self, line, nl):
        line = line.decode(self.charset or 'latin1')
        if not nl:
            raise MultipartError('Unexpected end of line in header.')
        if not line.strip():  # blank line -> end of header segment
            self.finish_header()
        elif line[0] in ' \t' and self.headerlist:
            name, value = self.headerlist.pop()
            self.headerlist.append((name, value + line.strip()))
        else:
            if ':' not in line:
                raise MultipartError("Syntax error in header: No colon.")
            name, value = line.split(':', 1)
            self.headerlist.append((name.strip(), value.strip()))

    def write_body(self, line, nl):
        if not line and not nl:
            return  # This does not even flush the buffer
        if self.content_transfer_encoding and not nl:
            raise MultipartError('Line too long on transfer_encoded chunk.')
        if self.content_transfer_encoding == 'quoted-printable':
            if line.endswith(tob('=')):
                nl = tob('')
            line = quopri.decodestring(line)
        elif self.content_transfer_encoding == 'base64':
            line, nl = binascii.a2b_base64(line), tob('')
        self.size += len(line) + len(self._buf)
        self.file.write(self._buf + line)
        self._buf = nl
        if self.content_length > 0 and self.size > self.content_length:
            raise MultipartError('Size of body exceeds Content-Length header.')
        if self.size > self.memfile_limit and isinstance(self.file, BytesIO):
            self.file, old = TemporaryFile(mode='w+b'), self.file
            old.seek(0)
            copy_file(old, self.file, self.size, self.buffer_size)

    def finish_header(self):
        self.file = BytesIO()
        self.headers = Headers(self.headerlist)
        cdis = self.headers.get('Content-Disposition', '')
        ctype = self.headers.get('Content-Type', '')
        if not cdis:
            raise MultipartError('Content-Disposition header is missing.')
        self.disposition, self.options = parse_options_header(cdis)
        self.name = self.options.get('name')
        self.filename = self.options.get('filename')
        self.content_type, options = parse_options_header(ctype)
        self.charset = options.get('charset') or self.charset
        self.content_length = int(self.headers.get('Content-Length', '-1'))
        self.content_transfer_encoding = \
                self.headers.get('Content-Transfer-Encoding')
        if self.content_transfer_encoding not in \
                [None, 'base64', 'quoted-printable']:
            raise MultipartError('invalid Content-Transfer-Encoding')

    def is_buffered(self):
        ''' Return true if the data is fully buffered in memory.'''
        return isinstance(self.file, BytesIO)

    def value(self, limit):
        ''' Data decoded with the specified charset '''
        pos = self.file.tell()
        try:
            self.file.seek(0)
            val = self.file.read(limit)
            if self.file.read(1):
                raise MultipartError("Request too big. Increase mem_limit.")
        finally:
            self.file.seek(pos)
        return val.decode(self.charset)

    def save_as(self, path):
        fp = open(path, 'wb')
        pos = self.file.tell()
        try:
            self.file.seek(0)
            size = copy_file(self.file, fp)
        finally:
            self.file.seek(pos)
        return size

##############################################################################
#################################### WSGI ####################################
##############################################################################


def parse_form_data(environ, charset='utf8', strict=False, **kw):
    ''' Parse form data from an environ dict and return a (forms, files) tuple.
        Both tuple values are dictionaries with the form-field name as a key
        (unicode) and lists as values (multiple values per key are possible).
        The forms-dictionary contains form-field values as unicode strings.
        The files-dictionary contains :class:`MultipartPart` instances, either
        because the form-field was a file-upload or the value is too big to fit
        into memory limits.

        :param environ: An WSGI environment dict.
        :param charset: The charset to use if unsure. (default: utf8)
        :param strict: If True, raise :exc:`MultipartError` on any parsing
                       errors. These are silently ignored by default.
    '''

    forms, files = MultiDict(), MultiDict()
    try:
        if environ.get('REQUEST_METHOD', 'GET').upper() not in ('POST', 'PUT'):
            raise MultipartError("Request method other than POST or PUT.")
        content_length = int(environ.get('CONTENT_LENGTH', '-1'))
        content_type = environ.get('CONTENT_TYPE', '')
        if not content_type:
            raise MultipartError("Missing Content-Type header.")
        content_type, options = parse_options_header(content_type)
        stream = environ.get('wsgi.input') or BytesIO()
        kw['charset'] = charset = options.get('charset', charset)
        mem_limit = kw.get('mem_limit', 2 ** 20)
        if content_type == 'multipart/form-data':
            boundary = options.get('boundary', '')
            if not boundary:
                raise MultipartError("No boundary for multipart/form-data.")
            for part in MultipartParser(stream, boundary, content_length,
                                        **kw):
                if part.filename:
                    files[part.name] = part
                else:
                    value = part.value(mem_limit)
                    mem_limit -= len(value)
                    forms[part.name] = value
        elif content_type in ('application/x-www-form-urlencoded',
                              'application/x-url-encoded'):
            if content_length > mem_limit:
                raise MultipartError("Request too big. Increase mem_limit.")
            data = stream.read(mem_limit).decode(charset)
            if stream.read(1):  # These is more that does not fit mem_limit
                raise MultipartError("Request too big. Increase mem_limit.")
            data = parse_qs(data, keep_blank_values=True)
            for key, values in item_iterator(data):
                for value in values:
                    forms[key] = value
        else:
            raise MultipartError("Unsupported content type.")
    except MultipartError:
        if strict:
            raise
    return forms, files


#######################

def form_parse(args):
    import io, base64
    body = args.get("__ow_body")
    method = args["__ow_method"]
    ctype = args["__ow_headers"]["content-type"]
    input = io.BytesIO(base64.b64decode(body))
    env = {
        'REQUEST_METHOD': method, 
        'CONTENT_TYPE': ctype, 
        'wsgi.input': input
    }
    return parse_form_data(env, strict=True, charset='utf-8')

#body = "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS05NTc0MmEwYmJkOGE5MjU3DQpDb250ZW50LURpc3Bvc2l0aW9uOiBmb3JtLWRhdGE7IG5hbWU9InBob3RvIjsgZmlsZW5hbWU9ImhlbGxvLnR4dCINCkNvbnRlbnQtVHlwZTogdGV4dC9wbGFpbg0KDQpoZWxsbwoNCi0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tOTU3NDJhMGJiZDhhOTI1Nw0KQ29udGVudC1EaXNwb3NpdGlvbjogZm9ybS1kYXRhOyBuYW1lPSJuYW1lIg0KDQpoZWxsbw0KLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS05NTc0MmEwYmJkOGE5MjU3DQpDb250ZW50LURpc3Bvc2l0aW9uOiBmb3JtLWRhdGE7IG5hbWU9ImVtYWlsIg0KDQpoQGwubw0KLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS05NTc0MmEwYmJkOGE5MjU3LS0NCg=="
#ctype = "multipart/form-data; boundary=------------------------95742a0bbd8a9257"
#args = { "__ow_body": body, "__ow_headers": { "content-type": ctype}, "__ow_method": "post" }


def main(args):
    from base64 import b64encode
    fields, files = form_parse(args)
    res = {}
    for k in fields:
        res[k] = fields[k]
    for k in files:
        file = files[k].file.read()
        res[k] = b64encode(file).decode('ascii')
    return { "body": res }
    #return {
    #    "body": "Redirect",
    #    "statusCode": 302,
    #    "headers": {
    #        "Location": "http://localhost:5000/app/index.html#/import/pippo"
    #    }
    #}

