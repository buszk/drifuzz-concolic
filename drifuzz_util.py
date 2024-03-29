import os
import json
import time
import socket
import struct
import shutil
import threading
from typing import Dict, Tuple, List
from cmdparser import opts, Command
from common import get_global_module

qemu_socket = '/tmp/zekun_drifuzz_socket_0'


class Fixer:
    def __init__(self, option=Dict[Tuple[int, int], List[Tuple[int, int]]]):
        self.option = option

    def fix_io(self, region, ioaddr, size, val):
        key = (region, ioaddr)
        if key in self.option:
            for offset, new_val in self.option[key]:
                assert offset <= size
                assert new_val >= 0 and new_val < 256
                val &= ~(0xff << (offset*8))
                val |= (new_val << (offset*8))
        return val


class SocketThread (threading.Thread):

    def __init__(self, model, addrses):
        threading.Thread.__init__(self)
        self.address = addrses
        self._stop_event = threading.Event()
        self.model = model

    def run(self):
        try:
            os.unlink(self.address)
        except OSError:
            if os.path.exists(self.address):
                raise

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.address)
        sock.listen(1)

        while not self.stopped():
            sock.settimeout(0.1)
            try:
                connection, _ = sock.accept()
                print("Got connection")
            except socket.timeout:
                continue
            try:
                connection.settimeout(0.1)
                while not self.stopped():
                    try:
                        ty: bytearray[8] = connection.recv(8)
                        if ty == b'':
                            print('Close connection: no more data')
                            break
                        _ty = struct.unpack('<Q', ty)[0]
                        opt = opts[Command(_ty)]
                        args: bytearray[opt['argbytes']
                                        ] = connection.recv(opt['argbytes'])
                        _args = struct.unpack(opt['argfmt'], args)
                        # print(_args)
                        ret = self.model.handle(
                            opts[Command(_ty)]['func'], *_args)
                        # print(ret)
                        # If VM request reset, we close the connection
                        if Command(_ty) == Command.REQ_RESET:
                            print('REQ_RESET')
                            break
                        if ret != None and opt['retfmt'] != '':
                            _ret = struct.pack(opt['retfmt'], *ret)
                            connection.send(_ret)
                        elif ret != None and isinstance(ret[0], bytes):
                            connection.send(ret[0])
                            connection.send(struct.pack('<Q', ret[1]))

                    except socket.timeout:
                        pass
                    except ConnectionResetError:
                        break

            finally:
                connection.close()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()


class CommandHandler:

    def __init__(self, gm, seed='random_seed', fixer=None, usb=False):
        self.gm = gm
        self.read_cnt: dict = {}
        self.dma_cnt: dict = {}
        self.fixer = fixer
        self.usb = usb

        if seed == '/dev/urandom':
            with open(seed, 'rb') as infile:
                self.payload = infile.read(0xffff)
                self.payload_len = len(self.payload)
        else:
            with open(seed, 'rb') as infile:
                self.payload = infile.read()
                self.payload_len = len(self.payload)

    def get_data_by_size(self, size, ind):
        # res = b''
        # if ind >= self.payload_len:
        #     res = b'\xaa' * size
        # elif ind + size > self.payload_len:
        #     res += self.payload[ind:self.payload_len]
        #     res += b'\xaa' * (ind + size - self.payload_len)
        # else:
        #     res += self.payload[ind:ind+size]
        # return res
        ii = ind % self.payload_len
        res = b''
        while ii + size > self.payload_len:
            res += self.payload[ii:self.payload_len]
            size -= (self.payload_len - ii)
            ii = 0
        res += self.payload[ii:ii+size]
        return res

    def bytes_to_int(self, bs):
        if (len(bs) == 1):
            return struct.unpack('<B', bs)[0]
        elif (len(bs) == 2):
            return struct.unpack('<H', bs)[0]
        elif (len(bs) == 4):
            return struct.unpack('<I', bs)[0]
        elif (len(bs) == 8):
            return struct.unpack('<Q', bs)[0]

    def get_read_idx(self, k, size):
        n = 0
        if k not in self.read_cnt.keys():
            self.read_cnt[k] = 1
        else:
            n = self.read_cnt[k]
            self.read_cnt[k] += 1

        return self.gm.get_read_idx(k, size, n)

    def get_read_data(self, k, size):
        idx = self.get_read_idx(k, size)
        data = self.get_data_by_size(size, idx)
        return (self.bytes_to_int(data), idx, )

    def get_dma_idx(self, k, size):
        n = 0
        if k not in self.dma_cnt.keys():
            self.dma_cnt[k] = 1
        else:
            n = self.dma_cnt[k]
            self.dma_cnt[k] += 1

        return self.gm.get_dma_idx(k, size, n, reuse=(True and not self.usb))

    def get_dma_data(self, k, size):
        idx = self.get_dma_idx(k, size)
        return (self.get_data_by_size(size, idx), idx, )

    def handle(self, type: str, *args):
        return getattr(self, f"handle_"+type)(*args)

    def handle_write(self, region, addr, size, val):
        # print("[%.4f] write #%d[%lx][%d] =  %x\n" % (time.time(), region, addr, size, val))
        pass

    def handle_read(self, region, addr, size):
        k = (region, addr, size)
        ret, idx = self.get_read_data(k, size)
        if self.fixer:
            assert self.fixer.fix_io
            ret = self.fixer.fix_io(region, addr, size, ret)
        # print("[%.4f] read  #%d[%lx][%d] as %x\n" % (time.time(), region, addr, size, ret))
        return (ret, idx, )

    def handle_dma_buf(self, size):
        ret, idx = self.get_dma_data(size, size)
        # print("[%.4f] dma_buf [%x]\n" % (time.time(), size))
        return (ret, idx, )

    def handle_reset(self):
        # TODO Check coverage
        pass

    def handle_exec_init(self):
        return (0,)

    def handle_exec_exit(self):
        return (0,)

    def handle_vm_ready(self):
        return (0,)

    def handle_vm_kasan(self):
        print("Found a bug reported by KASAN.")
        print("Check concolic.log for details")
        return (0,)

    def handle_req_reset(self):
        self.slave.restart_vm()

    def handle_exec_timeout(self):
        return (0,)


def json_dumper(obj):
    return obj.__dict__


class GlobalModel():

    def __init__(self, forcesave=False):
        self.next_free_idx = 0
        self.read_idx: dict = {}
        self.dma_idx: dict = {}
        self.last_key = (0, 0, 0)
        self.key_count = 0
        self.tosave = True
        self.forcesave=forcesave

    def __check_repeating_key(self, key, n=4000):
        if (key == self.last_key):
            self.key_count += 1
        else:
            self.key_count = 0
        self.last_key = key
        # print(key, self.key_count)
        if self.key_count > n:
            self.tosave = False

    def get_read_idx(self, key, size, cnt):
        if key in self.read_idx.keys():
            if cnt < len(self.read_idx[key]):
                return self.read_idx[key][cnt]
            elif cnt == len(self.read_idx[key]):
                self.__check_repeating_key(key)
                self.read_idx[key].append(self.next_free_idx)
                self.next_free_idx += size
                return self.read_idx[key][cnt]
            else:
                print("Error: read counter too large %d %d" %
                      (cnt, len(self.read_idx[key])))
                return 0
        elif cnt == 0:
            self.read_idx[key] = [self.next_free_idx]
            self.next_free_idx += size
            return self.read_idx[key][cnt]
        else:
            print("Error: non-zero counter for empty read list %d" % cnt)
            return 0

    def get_dma_idx(self, key, size, cnt, reuse=True):
        if key in self.dma_idx.keys():
            if reuse:
                return self.dma_idx[key][0]
            elif cnt < len(self.dma_idx[key]):
                return self.dma_idx[key][cnt]
            elif cnt == len(self.dma_idx[key]):
                # self.__check_repeating_key(key, n=1000)
                self.dma_idx[key].append(self.next_free_idx)
                self.next_free_idx += size
                return self.dma_idx[key][cnt]
            else:
                print("Error: dma counter too large %d %d" %
                      (cnt, len(self.dma_idx[key])))
                return 0
        elif cnt == 0:
            self.dma_idx[key] = [self.next_free_idx]
            self.next_free_idx += size
            return self.dma_idx[key][cnt]
        else:
            print("Error: non-zero counter for empty dma list %d" % cnt)
            return 0

    def save_data(self, target):
        if not self.forcesave and not self.tosave:
            print("Not saving because of repetitive query")
            return
        print('save_data', target)
        dump = {}
        args_to_save = ['next_free_idx', 'read_idx', 'dma_idx']
        for key, value in self.__dict__.items():
            if key == 'next_free_idx':
                dump[key] = value
            elif key == 'read_idx' or key == 'dma_idx':
                dump[key] = [{'key': k, 'value': v} for k, v in value.items()]

        with open(get_global_module(target),
                  'w') as outfile:
            json.dump(dump, outfile, default=json_dumper, indent=4)
        print('save_data done')

    def load_data(self, target):
        """
        Method to load an entire master state from JSON file...
        """
        if not os.path.exists(get_global_module(target)):
            return
        with open(get_global_module(target),
                  'r') as infile:
            dump = {}
            try:
                dump = json.load(infile)
            except json.decoder.JSONDecodeError:
                print("We have a corrupted model save")
                print("Try the backup file")
                with open(get_global_module(target) + ".bk", 'r') as f:
                    dump = json.load(f)
                shutil.copyfile(get_global_module(target)+".bk",
                                get_global_module(target))
            for key, value in dump.items():
                if key == 'next_free_idx':
                    setattr(self, key, value)
                elif key == 'read_idx' or key == 'dma_idx':
                    d = {}
                    for entry in value:
                        if isinstance(entry['key'], list):
                            k = tuple(entry['key'])
                        elif isinstance(entry['key'], int):
                            k = entry['key']
                        d[k] = entry['value']
                    setattr(self, key, d)
        shutil.copyfile(get_global_module(target),
                        get_global_module(target)+".bk")
