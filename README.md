# Testing kernel device drivers with concolic execution and binary rewriting

## Adding a tested program
### Find a target driver
```
cd linux
grep -rn PCI_DEVICE drivers/net/wireless
```

Choose one that you want to test

In Kconfig, find the corresponding CONFIG flag.
Add the following to Makefile.
```
KCOV_INSTRUMENT := y
ccflags-y += -fno-reorder-functions
```

### Build image
```
cd Drifuzz
# Add new CONFIG_{DRIVER}=m to build as loadable module
vim linux-module-build/.config
# Rememebr *.ko created
./compile.sh --build-module 
./compile.sh --build-image
```

### Create emulation driver in panda
* Create file `panda/drifuzz/hw/{DRIVER}.c`
* Add an entry to `panda/drifuzz/hw/Makefile.objs`
* Add the name to `panda/hw/pci/pci.c`'s `pci_nic_models` and `pci_nic_names` lists

## Build PANDA
```
cd Drifuzz
./compile.sh --build-panda
```

### Create snapshot
```
./snapshot_helper.py {DRIVER}

# In qemu, login with root
# Ctrl-A C
# (qemu) savevm {DRIVER}
# Ctrl-A D
```

### Troubleshooting
Run the following command. It should generate inputs with flipped branches in `work/{DRIVER}/out`.
```
./concolic.py {DRIVER} {INPUT}
```

## Testing
```
./search_group.py {DRIVER} {INPUT}
```