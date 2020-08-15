
from enum import IntEnum

class Command(IntEnum):
    WRITE = 1
    READ = 2
    DMA_BUF = 3
    EXEC_INIT = 4
    EXEC_EXIT = 5
    READY = 6
    VM_KASAN = 7
    REQ_RESET = 8
    EXEC_TIMEOUT = 9

opts = {
    Command.WRITE: {
        'func': 'write',
        'argbytes': 32,
        'argfmt': '<QQQQ',
        'retfmt': ''
    },
    Command.READ: {
        'func': 'read',
        'argbytes': 24,
        'argfmt': '<QQQ',
        'retfmt': '<Q'
    },
    Command.DMA_BUF: {
        'func': 'dma_buf',
        'argbytes': 8,
        'argfmt': '<Q',
        'retfmt': ''
    },
    Command.EXEC_INIT: {
        'func': 'exec_init',
        'argbytes': 0,
        'argfmt': '',
        'retfmt': '<Q'
    },
    Command.EXEC_EXIT: {
        'func': 'exec_exit',
        'argbytes': 0,
        'argfmt': '',
        'retfmt': '<Q'
    },
    Command.READY: {
        'func': 'vm_ready',
        'argbytes': 0,
        'argfmt': '',
        'retfmt': '<Q'
    },
    Command.VM_KASAN: {
        'func': 'vm_kasan',
        'argbytes': 0,
        'argfmt': '',
        'retfmt': ''
    },
    Command.REQ_RESET: {
        'func': 'req_reset',
        'argbytes': 0,
        'argfmt': '',
        'retfmt': ''
    },
    Command.EXEC_TIMEOUT: {
        'func': 'exec_timeout',
        'argbytes': 0,
        'argfmt': '',
        'retfmt': ''
    }
}