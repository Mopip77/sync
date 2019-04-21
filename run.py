import sys
import os

from src.backup.backup import BackUpUtil

if __name__ == "__main__":
    buu = BackUpUtil()
    # 不加会报 TERM environment variable not set
    # os.system("export TERM=linux && clear")

    args = sys.argv
    if len(args) == 1:
        buu.display()
        print("use `backupThem -h` to show more command arguments")
    else:
        if args[1] == 'a':
            buu.addNewReference()
        elif args[1] == 'm':
            buu.modifyRenference()
        elif args[1] == 'd':
            buu.delRenference()
        elif args[1] == 's':
            name = args[2] if len(args) >= 3 else None
            destIdx = args[3:] if len(args) >= 4 else None
            if destIdx is not None:
                destIdx = [int(idx) for idx in destIdx]
            buu.sync(name, destIdx)
        elif args[1] == '-h':
            print("""backupThem <command>
command arguments:
  a,                  add new reference
  m,                  modify existing reference
  d,                  delete existing reference
  s {Name Indxes},    synchronize the references with the Name, which destination indexes belongs to Indexes
            """)
        else:
            print("use `backupThem -h` to show more command arguments")