#!/usr/bin/env python3
import os
import socket
import struct
import json
import time
import pty
import threading
import subprocess
from struct import unpack
from cmdparser import opts, Command

qemu_socket = '/tmp/zekun_drifuzz_socket_0'
global_module_save = "global_module.sav"
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
                print("accepting")
                connection, _ = sock.accept()
                print("Got connection")
            except socket.timeout:
                    continue
            try:
                # connection.settimeout(0.1)
                while not self.stopped():
                    try:
                        ty: bytearray[8] = connection.recv(8)
                        if ty == b'':
                            break
                        print(ty)
                        _ty = struct.unpack('<Q', ty)[0]
                        opt = opts[Command(_ty)]
                        args:bytearray[opt['argbytes']] = connection.recv(opt['argbytes'])
                        _args = struct.unpack(opt['argfmt'], args)
                        # print(_args)
                        ret = self.model.handle(opts[Command(_ty)]['func'], *_args)
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

    def __init__(self, gm):
        self.gm = gm
        self.read_cnt:dict = {}
        self.dma_cnt:dict = {}
        
        with open("random_seed", 'rb') as infile:
            self.payload = infile.read()
            print(type(self.payload))
            self.payload_len = len(self.payload)

    def get_data_by_size(self, size, ind):
        ii = ind % self.payload_len
        res = b''
        while ii + size >self.payload_len:
            res += self.payload[ii:self.payload_len]
            size -= (self.payload_len - ii)
            ii = 0
        res += self.payload[ii:ii+size]
        return res
    
    def bytes_to_int(self, bs):
        if (len(bs) == 1):
            return unpack('<B', bs)[0]
        elif (len(bs) == 2):
            return unpack('<H', bs)[0]
        elif (len(bs) == 4):
            return unpack('<I', bs)[0]
        elif (len(bs) == 8):
            return unpack('<Q', bs)[0]

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

        return self.gm.get_dma_idx(k, size, n, reuse=False)

        
    def get_dma_data(self, k, size):
        idx = self.get_dma_idx(k, size)
        return (self.get_data_by_size(size, idx), idx, )

    
    def handle(self, type:str, *args):
        return getattr(self, f"handle_"+type)(*args)

        
    def handle_write(self, region, addr, size, val):
        print("[%.4f] write #%d[%lx][%d] =  %x\n" % (time.time(), region, addr, size, val))

    def handle_read(self, region, addr, size):
        k = (region, addr, size)
        ret, idx = self.get_read_data(k, size)
        print("[%.4f] read  #%d[%lx][%d] as %x\n" % (time.time(), region, addr, size, ret))
        return (ret, idx, )
    
    def handle_dma_buf(self, size):
        ret, idx = self.get_dma_data(size)
        print("[%.4f] dma_buf [%x]\n" % (time.time(), size))
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
        return (0,)

    def handle_req_reset(self):
        self.slave.restart_vm()
    
    def handle_exec_timeout(self):
        return (0,)


def json_dumper(obj):
    return obj.__dict__


class GlobalModel():
    
    def __init__(self):
        self.next_free_idx = 0
        self.read_idx:dict = {}
        self.dma_idx:dict = {}

    def get_read_idx(self, key, size, cnt):
        if key in self.read_idx.keys():
            if cnt < len(self.read_idx[key]):
                return self.read_idx[key][cnt]
            elif cnt == len(self.read_idx[key]):
                self.read_idx[key].append(self.next_free_idx)
                self.next_free_idx += size
                return self.read_idx[key][cnt]
            else:
                print("Error: read counter too large %d %d" % (cnt, len(self.read_idx[key])))
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
                self.dma_idx[key].append(self.next_free_idx)
                self.next_free_idx += size
                return self.dma_idx[key][cnt]
            else:
                print("Error: dma counter too large %d %d" % (cnt, len(self.dma_idx[key])))
                return 0
        elif cnt == 0:
            self.dma_idx[key] = [self.next_free_idx]
            self.next_free_idx += size
            return self.dma_idx[key][cnt]
        else:
            print("Error: non-zero counter for empty dma list %d" % cnt)
            return 0



    def save_data(self):
        dump = {}
        args_to_save = ['next_free_idx', 'read_idx', 'dma_idx']
        for key, value in self.__dict__.items():
            if key == 'next_free_idx':
                dump[key] = value
            elif key == 'read_idx' or key == 'dma_idx':
                dump[key] = [{'key': k, 'value': v} for k, v in value.items()]

        with open(global_module_save, \
                        'w') as outfile:
            json.dump(dump, outfile, default=json_dumper)

    def load_data(self):
        """
        Method to load an entire master state from JSON file...
        """
        with open(global_module_save, \
                        'r') as infile:
            dump = json.load(infile)
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

env={"LD_LIBRARY_PATH":"/home/zekun/bpf/install/lib"}   

class Panda:
    def __init__(self):
        self.cmd = ["python2", "./analyze.py",
            "--record", "--replay",
            "--target", "alx",
            "--socket", qemu_socket]

    def run(self):
        print(" ".join(self.cmd))
        master, slave = pty.openpty()
        self.process = subprocess.Popen(self.cmd,
                                        stdin=slave,
                                        stdout=None,
                                        stderr=None,
                                        env=env)
        self.process.wait()

def concolic_record():
    global_module = GlobalModel()
    command_handler = CommandHandler(global_module)
    socket_thread = SocketThread(command_handler, qemu_socket)

    socket_thread.start()

    time.sleep(.1)

    panda = Panda()
    panda.run()
    socket_thread.stop()

def main():
    concolic_record()


if __name__ == "__main__":
    main()
