#!/usr/bin/env python2
#-*- coding:utf-8 -*-

import json, os, sys, socket, httplib, datetime, time, getopt
from baidupcsapi import PCS
from cmd2 import Cmd, make_option, options
import requests, ssl
try:
    # disable warning: InsecureRequestWarning: Unverified HTTPS request is being made. Adding certificate verification is strongly advised. See: https://urllib3.readthedocs.org/en/latest/security.html
    requests.packages.urllib3.disable_warnings()
except:
    pass

try:
    from termcolor import colored
except:
    def colored(text, color=None, on_color=None, attrs=None):
        return text

reload(sys)
sys.setdefaultencoding('utf8')

if not sys.stdout.isatty():
    import codecs
    sys.stdout = codecs.getwriter('utf8')(sys.stdout)
    sys.stderr = codecs.getwriter('utf8')(sys.stderr)

CWD = os.path.dirname(os.path.realpath(__file__))

def readable_size(num, use_kibibyte = True, unit_ljust = 0):
    base, suffix = [(1000.,'B'),(1024.,'iB')][use_kibibyte]
    for x in ['B'] + map(lambda x: x+suffix, list('kMGTP')):
        if -base < num < base:
            return "%3.1f %s" % (num, x.ljust(unit_ljust, ' '))
        num /= base
    return "%3.1f %s" % (num, x.ljust(unit_ljust, ' '))

def readable_timedelta(num):
    num = int(num)
    assert num >= 0
    return str(datetime.timedelta(seconds = num))

def log(s, color = None, on_color = None, attrs = None, new_line = True, timestamp = True, f = sys.stderr):
    if timestamp is True:
        now = datetime.datetime.now().strftime('[%Y-%m-%d_%H:%M:%S]')
    elif timestamp is False:
        now = None
    elif timestamp:
        now = timestamp
    if not color:
        s = str(s)
    else:
        s = colored(str(s), color, on_color, attrs)
    if now:
        f.write(now)
        f.write(' ')
    f.write(s)
    if new_line:
        f.write('\n')
    f.flush()

def split_command_line(command_line):       # this piece of code comes from pexcept, thanks very much!

    '''This splits a command line into a list of arguments. It splits arguments
    on spaces, but handles embedded quotes, doublequotes, and escaped
    characters. It's impossible to do this with a regular expression, so I
    wrote a little state machine to parse the command line. '''

    arg_list = []
    arg = ''

    # Constants to name the states we can be in.
    state_basic = 0
    state_esc = 1
    state_singlequote = 2
    state_doublequote = 3
    # The state when consuming whitespace between commands.
    state_whitespace = 4
    state = state_basic

    for c in command_line:
        if state == state_basic or state == state_whitespace:
            if c == '\\':
                # Escape the next character
                state = state_esc
            elif c == r"'":
                # Handle single quote
                state = state_singlequote
            elif c == r'"':
                # Handle double quote
                state = state_doublequote
            elif c.isspace():
                # Add arg to arg_list if we aren't in the middle of whitespace.
                if state == state_whitespace:
                    # Do nothing.
                    None
                else:
                    arg_list.append(arg)
                    arg = ''
                    state = state_whitespace
            else:
                arg = arg + c
                state = state_basic
        elif state == state_esc:
            arg = arg + c
            state = state_basic
        elif state == state_singlequote:
            if c == r"'":
                state = state_basic
            else:
                arg = arg + c
        elif state == state_doublequote:
            if c == r'"':
                state = state_basic
            else:
                arg = arg + c

    if arg != '':
        arg_list.append(arg)
    return arg_list

def parse_index_param(s, mx):
    ret = []
    if not s:
        return ret
    for i in s.split(','):
        ay = []
        if '-' in i:
            st, ed = map(int, i.split('-'))
            ay = range(st, ed+1)
        else:
            ay = [int(i)]
        for j in ay:
            if j >= mx:
                raise Exception('invalid file index: %d' % j)
            else:
                ret.append(j)
    return list(set(ret))

def handle_captcha(img_content, out = sys.stderr):
    try:
        from PIL import Image
    except:
        import Image
    from cStringIO import StringIO

    character = u'▄'

    CUBE_STEPS = [0x00, 0x5F, 0x87, 0xAF, 0xD7, 0xFF]
    BASIC16 = ((0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0),
               (0, 0, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229),
               (127, 127, 127), (255, 0, 0), (0, 255, 0), (255, 255, 0),
               (92, 92, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255))

    def xterm_to_rgb(xcolor):
        assert 0 <= xcolor <= 255
        if xcolor < 16:
            # basic colors
            return BASIC16[xcolor]
        elif 16 <= xcolor <= 231:
            # color cube
            xcolor -= 16
            return (CUBE_STEPS[(xcolor / 36) % 6],
                    CUBE_STEPS[(xcolor / 6) % 6],
                    CUBE_STEPS[xcolor % 6])
        elif 232 <= xcolor <= 255:
            # gray tone
            c = 8 + (xcolor - 232) * 0x0A
            return (c, c, c)

    COLOR_TABLE = [xterm_to_rgb(i) for i in xrange(256)]

    def rgb_to_xterm(r, g, b):
        if r < 5 and g < 5 and b < 5:
            return 16
        best_match = 0
        smallest_distance = 10000000000
        for c in xrange(16, 256):
            d = (COLOR_TABLE[c][0] - r) ** 2 + \
                (COLOR_TABLE[c][1] - g) ** 2 + \
                (COLOR_TABLE[c][2] - b) ** 2
            if d < smallest_distance:
                smallest_distance = d
                best_match = c
        return best_match

    def printPixels(rgb1,rgb2):
        c1 = rgb_to_xterm(rgb1[0], rgb1[1],rgb1[2])
        c2 = rgb_to_xterm(rgb2[0], rgb2[1],rgb2[2])
        out.write('\x1b[48;5;%d;38;5;%dm' % (c1, c2))
        out.write(character)

    def printImage(im, w, h):
        for y in range(0,h-1,2):
            for x in range(w):
                p1 = im.getpixel((x,y))
                p2 = im.getpixel((x,y+1))
                printPixels(p1, p2)
            print('\x1b[0m')

    def iterateImages(im, w, h):
        out.write('\x1b[s')

        while True:
            out.write('\x1b[u')
            printImage(im.convert('RGB'), w, h)

            try:
                im.seek(im.tell()+1)
                # for GIF
                time.sleep(im.info['duration']/1000.0)
            except EOFError:
                break

    img_data = StringIO(img_content)
    im = Image.open(img_data)
    save_path = os.path.join(CWD, '.baiduyun-captcha.png')
    im.save(save_path)
    imgWidth = im.size[0]
    imgHeight = im.size[1]

    iterateImages(im, imgWidth, imgHeight)

    prompt = 'Please enter captcha below, if the image displayed in console is not clear, open the following file:\n%s\nenter captcha > ' % save_path
    verifycode = raw_input(prompt)
    return verifycode

def download(pcs, filepath, saveto, blocksize = 1<<21, retry = 5):
    log('[ II ] downloading `%s` to `%s` [blocksize = %d, retry = %d]' % (filepath, saveto, blocksize, retry), 'white')

    o = json.loads(pcs.meta([filepath]).content)
    if o['errno'] != 0:
        log('[ WW ] invalid download request: %r, error = %s' % (filepath, json.dumps(o)))
        return

    size = o['info'][0]['size']

    log(u'[ II ] server_filename = %s, size = %d, md5 = %s' % (o['info'][0]['server_filename'], size, o['info'][0]['md5']), 'cyan')

    dn = os.path.dirname(saveto)
    if not os.path.exists(dn): os.makedirs(dn)

    f = open(saveto, 'a')

    cur_size = f.tell()
    start = cur_size

    if cur_size == size:
        log('[ II ] file already downloaded, size = %d' % size, 'cyan')
    elif cur_size > size:
        log('[ WW ] file size larger than server file size: %d > %d' % (cur_size, size), 'yellow')
    elif cur_size > 0:
        log('[ II ] continue downloading from offset %d' % cur_size, 'cyan')
    else:
        log('[ II ] start downloading from beginning...', 'cyan')

    begin_time = time.time()
    downloaded = 0

    while start < size:
        end = start + blocksize
        if end > size: end = size
        headers = {'Range': 'bytes=%d-%d' % (start, end - 1)}
        done = False
        sleep = 1
        data_read = 0
        for i in range(retry):
            try:
                round_time = time.time()
                res = pcs.download(filepath, headers = headers, timeout = 12 * sleep)
                if res.status_code >= 200 and res.status_code < 300:
                    done = True
                    data_read = len(res.content)
                    downloaded += data_read
                    now = time.time()
                    ave = downloaded / (now - begin_time)
                    log('[ II ] downloaded size = %d/%d (%.2f%%), just downloaded %d bytes, speed = %s/s, average speed = %s/s, remain time = %s' % (start + data_read, size, (start + data_read) * 100.0/size, data_read, readable_size(data_read / (now - round_time)), readable_size(ave), readable_timedelta((size - start - data_read)/ave)))
                    f.write(res.content)
                    break
                else:
                    log('[ WW ] response code = %d, sleeping for %d seconds' % (res.status_code, sleep), 'yellow', timestamp = True)
            except requests.exceptions.Timeout:
                log('[ WW ] request timed out, sleeping for %d seconds' % (sleep), 'yellow', timestamp = True)
            except requests.exceptions.ConnectionError:
                log('[ WW ] request ConnectionError, sleeping for %d seconds' % (sleep), 'yellow', timestamp = True)
            except ssl.SSLError as err:
                log('[ WW ] ssl error: %s, sleeping for %d seconds' % (str(err), sleep), 'yellow', timestamp = True)
            time.sleep(sleep)
            sleep *= 2
        if not done:
            log('[ EE ] retried %d times but still failed' % retry, 'red', timestamp = True)
            break
        if data_read == end - start:
            start = end
        else:
            log('[ WW ] we requested %d = %d - %d, but only got %d' % (end - start, end, start, data_read), 'yellow')
            start += data_read

    f.close()
    log('[ II ] file `%s` downloaded, a total of %d bytes downloaded within %s, md5 = %s.' % (filepath, size, readable_timedelta(time.time() - begin_time), o['info'][0]['md5']), 'white')

class BaiduPan(Cmd):
    prompt = colored('dupan', 'yellow', attrs = ['bold']) + colored(' >> ', 'red', attrs = ['bold'])
    completekey = 'tab'
    editor = 'vim'
    timing = False
    debug = True

    download_root = os.path.join(CWD, 'download')
    cwd = '/'
    dirs = {}
    pcs = None

    def __init__(self):
        Cmd.__init__(self)
        try:
            import readline
            readline.set_completer_delims(' \t\n"') # initially it was ' \t\n`!@#$^&*()=+[{]}\\|;:\'",<>?', but I dont want to break on too many
        except:
            pass

    @options([make_option('-u', '--username', help="specify username"),
              make_option('-p', '--password',help="specify password"),
             ])
    def do_login(self, args, opts):
        print 'logging in, please wait ...'
        self.pcs = PCS(opts.username, opts.password, captcha_callback = handle_captcha)
        self.pcs.get_fastest_pcs_server()
        res = json.loads(self.pcs.quota().content)
        if res['errno'] != 0:
            self.pcs = None
            print 'login failed: %r' % res
            return
        print 'Login success. storage used: %s/%s' % (readable_size(res['used']), readable_size(res['total']))

    def do_cd(self, args):
        if type(args) == type([]):
            args = args[0]

        if not isinstance(args, basestring) or not args:
            print 'cd /path/to/dir'
            return

        if args.startswith('/'):
            self.cwd = args
        else:
            self.cwd = os.path.join(self.cwd, args)
        self.cwd = os.path.normpath(self.cwd)

    def do_timing(self, args):

        if not args:
            print 'timing on|off'
            return

        if args.lower() == 'on':
            self.timing = True
        elif args.lower() == 'off':
            self.timing = False
        else:
            print 'timing on|off'
            return

    def do_pwd(self, args):
        print self.cwd

    def do_saveto(self, args):
        path = args

        if not path:
            print 'current download root: %s' % self.download_root
            return

        if not path.startswith('/'):
            path = os.path.normpath(os.path.join(os.getcwd(), path))

        self.download_root = path
        print 'will save to %s' % path

    def do_ls(self, args):
        if not self.pcs:
            print 'please login first'
            return

        if not args:
            path = self.cwd
        else:
            path = args

        path = os.path.normpath(os.path.join(self.cwd, path))

        print path
        res = json.loads(self.pcs.list_files(path).content)

        # print json.dumps(res, indent = 4)
        '''
        {
            "isdir": 1,
            "category": 6,
            "server_filename": "cs",
            "local_mtime": 1395372049,
            "server_ctime": 1395372049,
            "server_mtime": 1395372049,
            "fs_id": 640464281820244,
            "path": "/cs",
            "size": 0,
            "local_ctime": 1395372049
        }
        '''

        if res.get('errno', None) != 0:
            log('invalid response: %r' % res, 'yellow')
            return

        print 'total %d' % len(res.get('list', []))

        content = []
        cnt = 0
        lst = res.get('list', [])
        idxsz = len(str(len(lst)-1))
        sizes = []
        sizesz = 0
        for fsitem in lst:
            t = readable_size(fsitem.get('size'))
            if len(t) > sizesz:
                sizesz = len(t)
            sizes.append(t)
        for i, fsitem in enumerate(lst):
            print '[ %s ]  %s  %s  %s   %s' % (str(cnt).ljust(idxsz), fsitem.get('isdir', 0) and 'd' or '-', sizes[i].ljust(sizesz, ' '), datetime.datetime.fromtimestamp(fsitem.get('server_mtime', 0)).strftime('%Y-%m-%d_%H:%M:%S'), colored(fsitem.get('server_filename'), fsitem.get('isdir', 0) and 'cyan' or 'white', attrs = ['bold']) + (fsitem.get('isdir', 0) and '/' or ''))
            cnt += 1
            content.append(fsitem.get('server_filename'))

        self.dirs[path] = lst

    @options([make_option('-i', '--index', help="the file index to delete, separate with comma, e.g. 3,5,2, also range supported, e.g. 1-4,5,7"),
             ])
    def do_meta(self, args, opts):
        if not self.pcs:
            print 'please login first'
            return

        args = split_command_line(args)

        fps = []
        if opts.index:
            if not self.dirs.get(self.cwd):
                print 'please use `ls` to list dir first to let me know which files you want to operate'
                return
            try:
                indexes = parse_index_param(opts.index, len(self.dirs.get(self.cwd)))
                fps = [self.dirs.get(self.cwd)[i]['server_filename'] for i in indexes]
            except Exception, ex:
                print ex
                return

        final = fps + args

        for path in final:
            path = os.path.normpath(os.path.join(self.cwd, path))

            print path
            o = json.loads(self.pcs.meta([path]).content)

            if o.get('errno', None) != 0:
                print ('invalid request: %r' % o)
                return

            size = o['info'][0]['size']

            info = o['info'][0]
            for k in info:
                print colored(k + ': ', 'cyan'), colored(info[k], 'white')

    def _complete_remote(filter = None):
        if not filter: filter = lambda x:True
        def complete_sth(self, text, line, start_index, end_index):
            if text:
                # list dir first it the user indicate that it's a dir
                if text.endswith('/'):
                    text = os.path.normpath(text)
                    dn = os.path.normpath(os.path.join(self.cwd, text))
                    prefix = text.startswith('/') and dn or text
                    if dn in self.dirs:
                        return map(lambda x: os.path.join(prefix, x), [e['server_filename'] for e in self.dirs.get(dn) if filter(e)])
                    else:
                        return []

                # check if it's a dir second, if it is, return appending slash
                if os.path.normpath(os.path.join(self.cwd, text)) in self.dirs:
                    return [text + '/']

                bn = os.path.basename(text)
                prefix = text[:-len(bn)]
                dn = os.path.dirname(os.path.normpath(os.path.join(self.cwd, text)))

                if dn not in self.dirs: return []

                ret = [os.path.join(prefix, e['server_filename']) + (((e['server_filename'] == bn) and e['isdir']) and '/' or '') for e in self.dirs.get(dn) if e['server_filename'].startswith(bn) and filter(e)]
                return ret
            else:
                return [e['server_filename'] for e in self.dirs.get(self.cwd) if filter(e)]
        return complete_sth

    complete_mv = complete_meta = complete_rm = complete_ls = _complete_remote()
    complete_cd = _complete_remote(filter = lambda e: e['isdir'])
    complete_download = _complete_remote(filter = lambda e: not e['isdir'])

    @options([make_option('-b', '--blocksize', type="int", default=1<<21, help="download blocksize"),
              make_option('-r', '--retry', type="int", default=5, help="retry time after failure"),
              make_option('-i', '--index', help="the file index to download, separate with comma, e.g. 3,5,2, also range supported, e.g. 1-4,5,7"),
             ])
    def do_download(self, args, opts):
        if not self.pcs:
            print 'please login first'
            return

        args = split_command_line(args)

        fps = []
        if opts.index:
            if not self.dirs.get(self.cwd):
                print 'please use `ls` to list dir first to let me know which files you want to operate'
                return
            try:
                indexes = parse_index_param(opts.index, len(self.dirs.get(self.cwd)))
                fps = [self.dirs.get(self.cwd)[i]['server_filename'] for i in indexes]
            except Exception, ex:
                print ex
                return

        final = fps + args
        if not final:
            print 'download [-i 3,5] relpath|/path/to/somefile'
            return
        log('[ II ] downloading %d files: %s' % (len(final), ', '.join(map(lambda x: '`' + x + '\'', final))), 'white')
        for filepath in final:
            if not filepath: continue
            if not filepath.startswith('/'):
                filepath = os.path.normpath(os.path.join(self.cwd, filepath))
            download(self.pcs, filepath, os.path.normpath(self.download_root + '/' + filepath), opts.blocksize, opts.retry)

    def do_mkdir(self, args):
        if not self.pcs:
            print 'please login first'
            return
        args = split_command_line(args)
        if not args:
            print 'mkdir /path/to/dir|relpath'
            return
        for p in args:
            ap = os.path.normpath(os.path.join(self.cwd, p))
            rs = json.loads(self.pcs.mkdir(ap).content)
            if rs['errno'] == 0:
                print rs['name'], 'created'
                dn = os.path.dirname(ap)
                if dn not in self.dirs:
                    self.dirs[dn] = []
                self.dirs[dn].append({
                    "isdir": 1,
                    "server_filename": os.path.basename(rs.get('name')),
                    "server_ctime": rs.get('mtime'),
                    "server_mtime": rs.get('mtime'),
                    "fs_id": rs.get('fs_id'),
                    "path": rs.get('path'),
                    "size": 0,
                })
            else:
                print rs['name'], 'failed'

    @options([make_option('-i', '--index', help="the file index to delete, separate with comma, e.g. 3,5,2, also range supported, e.g. 1-4,5,7"),
             ])
    def do_rm(self, args, opts):
        if not self.pcs:
            print 'please login first'
            return
        args = split_command_line(args)

        fps = []
        if opts.index:
            if not self.dirs.get(self.cwd):
                print 'please use `ls` to list dir first to let me know which files you want to operate'
                return
            try:
                indexes = parse_index_param(opts.index, len(self.dirs.get(self.cwd)))
                fps = [self.dirs.get(self.cwd)[i]['server_filename'] for i in indexes]
            except Exception, ex:
                print ex
                return

        final = fps + args

        if not final:
            print 'rm [-i 1-3,5] /path/to/dir|relpath'
            return
        for i in range(len(final)):
            final[i] = os.path.normpath(os.path.join(self.cwd, final[i]))
        print colored('deleting %r' % final, 'white')
        o = json.loads(self.pcs.delete(final).content)
        if o['errno'] == 0:
            for i in o['info']:
                print i['path'], 'deleted'
        else:
            print 'dir entity not exist, cannot delete, error: %r' % o

    @options([make_option('-i', '--index', help="the file index to move, separate with comma, e.g. 3,5,2, range also supported, e.g. 1-4,5,7"),
             ])
    def do_mv(self, args, opts):
        if not self.pcs:
            print 'please login first'
            return
        args = split_command_line(args)

        def usage():
            print 'mv {[file...] | -i 1-4,5,7} /dest/dir'
            print 'mv {[file...] | -i 1-4,5,7} /dest/dir/filename'
            
        if opts.index and len(args) < 1 or (not opts.index and len(args) < 2):
            print 'insufficent arguments: opts.index = %s, len(args) = %d' % (opts.index, len(args))
            usage()
            return

        fps = []
        if opts.index:
            if not self.dirs.get(self.cwd):
                print 'please use `ls` to list dir first to let me know which files you want to operate'
                return
            try:
                indexes = parse_index_param(opts.index, len(self.dirs.get(self.cwd)))
                fps = [self.dirs.get(self.cwd)[i]['server_filename'] for i in indexes]
            except Exception, ex:
                print ex
                return

        final = fps + args[:-1]
        dest = args[-1]
        endswithslash = dest.endswith('/')

        for i in range(len(final)):
            final[i] = os.path.normpath(os.path.join(self.cwd, final[i]))

        dest = os.path.normpath(os.path.join(self.cwd, dest))

        if not final or not dest:
            usage()
            return
        
        if len(final) > 1 or endswithslash:
            op = 'move'
        else:
            op = 'rename'

        if op == 'move':
            print colored('moving %r -> %s' % (final, dest), 'white')
            rs = self.pcs.move(final, dest)
        else:
            print colored('renaming %s -> %s' % (final[0], os.path.basename(dest)), 'white')
            rs = self.pcs.rename([(final[0], os.path.basename(dest))])
        
        o = json.loads(rs.content)
        if o['errno'] == 0:
            print '%s success' % op
        else:
            print '%s failed: %r' % (op, o)

    def do_rapid_upload(self, args):
        args = split_command_line(args)

        if len(args) < 2:
            print 'upload localfile /path/to/dest/dir'
            return

        dest = os.path.join(self.cwd, args[-1])
        src = args[0]
        dest = os.path.normpath(os.path.join(dest, os.path.basename(src)))

        print colored('rapid uploading %s' % src, 'white')
        if not os.path.exists(src):
            print colored('file %s not exist' % src, 'yellow')
            return
        rs = self.pcs.rapidupload(open(src, 'rb'), dest)
        o = json.loads(rs.content)
        if 'errno' in o and o['errno']:
            print '%s failed to rapid upload, reason = %r' % o
        else:
            print '%s rapid uploaded!' % (src)
            info = o['info']
            for k in info:
                print colored(k + ': ', 'cyan'), colored(info[k], 'white')

    def do_upload(self, args):
        args = split_command_line(args)
        if len(args) < 2:
            print 'upload [list of local file] /path/to/dest/dir'
            return

        class ProgressBar():
            def __init__(self, filename, skip = (1<<20)):
                self.first_call = True
                self.filename = filename
                self.finished = False
                self.skip = skip
                self.last = 0
                self.begin_time = time.time()
            def __call__(self, *args, **kwargs):
                if self.finished: return
                if self.first_call:
                    pass
                    self.first_call = False
        
                if kwargs['size'] <= kwargs['progress']:
                    print 'finished uploading %s' % self.filename
                    self.finished = True
                    return

                if kwargs['progress'] - self.last >= self.skip:
                    now = time.time()
                    avspeed = kwargs['progress'] / (now - self.begin_time)

                    self.last = kwargs['progress']
                    print 'uploading %s, progress = %d/%d (%.2f%%), average speed = %s/s, remain time = %s' % (self.filename, kwargs['progress'], kwargs['size'], kwargs['progress']*100.0/kwargs['size'], readable_size(avspeed), readable_timedelta((kwargs['size']-kwargs['progress'])/avspeed))

        dest = os.path.normpath(os.path.join(self.cwd, args[-1]))

        for i in args[:-1]:
            print colored('uploading %s to %s' % (i, dest), 'white')
            if not os.path.exists(i):
                print colored('file %s not exist' % i, 'yellow')
                continue
            rs = self.pcs.upload(dest, open(i, 'rb'), os.path.basename(i), callback = ProgressBar(i))
            o = json.loads(rs.content)
            if 'errno' in o and o['errno']:
                print '%s failed to upload, reason = %r' % o
                break
            else:
                print '%s uploaded to %s!' % (i, dest)
                dn = os.path.dirname(o.get('path'))
                if dn and dn not in self.dirs:
                    self.dirs[dn] = []
                if dn and dn in self.dirs:
                    self.dirs[dn].append({
                        "isdir": 0,
                        "server_filename": os.path.basename(o.get('path')),
                        "server_ctime": o.get('mtime'),
                        "server_mtime": o.get('mtime'),
                        "fs_id": o.get('fs_id'),
                        "path": o.get('path'),
                        "size": o.get('size'),
                    })

    def complete_upload(self, text, line, start_index, end_index):
        dn = os.path.dirname(text)
        bn = os.path.basename(text)
        # print '\ntext = %r, line = %r, dn = %s, bn = %s, start = %d, end = %d' % (text, line, dn, bn, start_index, end_index)
        ret = []
        if not os.path.exists(dn): return ret
        fns = os.listdir(dn)
        ret = []
        for i in fns:
            if i.startswith(bn):
                com = os.path.join(dn, i)
                if os.path.isdir(com):
                    com = os.path.normpath(com) + '/'
                ret.append(com)
        return ret

    complete_rapid_upload = complete_upload

    def do_sleep(self, args):
        t = float(args)
        time.sleep(t)
        print 'just slept %f seconds, ah, what a great day!' % t

    def do_EOF(self, line):
        print ''
        return True

if __name__ == '__main__':
    # usage: ./dupan.py 'login -u $username -p $password'
    BaiduPan().cmdloop()
