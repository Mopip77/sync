import os
import shutil
import yaml
import json

from threading import Thread
from multiprocessing.pool import Pool
from multiprocessing import Manager
from src.utils.mytime import getStrfTime, parseStrfTime
from src.utils.myfile import fileLastModifyTime, getSubfolderAndFiles
from src.trash_manager.trash_manager import TrashManager
from src.remote_transport.server_transporter import ServerTransporter
from src.font_color import font_color as FC

attachCommandRemoteConfigQueue = Manager().list()


class BackUpUtil():
    rootPath = '/'.join(os.path.realpath(__file__).split('/')[:-3])
    configPath = os.path.join(rootPath, 'config.yaml')
    referencePath = os.path.join(rootPath, 'folder_reference.json')

    def __init__(self, syncNames=None):
        self.dateTimePattern = None
        self.defaultDestPath = None
        self.trashPath = None
        self._loadConfig()
        self.folderRefernece = self._getFolderReference()

    def _loadConfig(self):
        with open(self.configPath, 'r') as f:
            config = f.read()
        config = yaml.load(config, Loader=yaml.BaseLoader)

        self.dateTimePattern = config['DATETIME_PATTERN']
        self.defaultDestPath = config['DEFAULT_DESTPATH']
        self.trashPath = config['TRASH_FOLDER_PATH']

    def _getFolderReference(self):
        fp = open(self.referencePath, 'r')
        folderReference = json.load(fp)
        fp.close()
        return folderReference

    def _updateFolderReference(self):
        fp = open(self.referencePath, 'w')
        fp.write(json.dumps(self.folderRefernece))
        fp.close()

    def _desktopNotify(self):
        text = '\n'.join([_['src'] for _ in self.folderRefernece])
        title = "备份完成,同步了{}个文件夹".format(len(self.folderRefernece))
        os.system('notify-cron -t 5000 "{}" "{}"'.format(title, text))

    def _syncFiles(self, curSrcPath, srcFiles, curDestPath, destFiles, lastSyncTime, destRootPath, remote, trashbin):
        """同步curSrcPath文件夹的所有文件到目标文件夹同级的位置"""
        uselessFiles = destFiles.difference(srcFiles)
        newFiles = srcFiles.difference(destFiles)

        # 目标文件夹无用文件
        for f in uselessFiles:
            destPath = os.path.join(curDestPath, f)
            print(FC.r("[Del ] ") + f)
            trashbin.moveToTrashbin(destPath, destRootPath)
            for r in remote:
                r.rm(destPath[len(destRootPath)+1:])

        # 新增文件
        for f in newFiles:
            srcPath = os.path.join(curSrcPath, f)
            destPath = os.path.join(curDestPath, f)
            print(FC.y("[New ] ") + f)
            shutil.copy(
                srcPath,
                destPath
            )
            for r in remote:
                r.put(srcPath, destPath[len(destRootPath)+1:])

        # 都有的文件
        for f in destFiles.intersection(srcFiles):
            _src_f = os.path.join(curSrcPath, f)
            _dest_f = os.path.join(curDestPath, f)

            if lastSyncTime is not None and fileLastModifyTime(_src_f) <= lastSyncTime:
                continue

            self._syncFile(_src_f, _dest_f, destRootPath, remote, trashbin)

    def _syncFile(self, srcFile, destFile, destRootPath, remote, trashbin):
        """比较并同步单个文件"""
        # 大小不同直接复制
        if os.stat(srcFile).st_size != os.stat(destFile).st_size:
            print(FC.r("[Diff] ") + srcFile.split('/')[-1])
            trashbin.moveToTrashbin(destFile, destRootPath)
            shutil.copy(srcFile, destFile)
            for r in remote:
                r.put(srcFile, destFile[len(destRootPath)+1:])
            return

        with open(srcFile, 'rb') as f1, open(destFile, 'rb') as f2:
            while True:
                data1 = f1.read(4096)
                data2 = f2.read(4096)
                if data1 != data2:
                    trashbin.moveToTrashbin(destFile, destRootPath)
                    shutil.copy(srcFile, destFile)
                    for r in remote:
                        r.put(srcFile, destFile[len(destRootPath)+1:])
                    print(FC.r("[Diff] ") + srcFile.split('/')[-1])
                    return
                elif data1 == b'':
                    print(FC.g("[Same] ") + srcFile.split('/')[-1])
                    return

    def _syncFolders(self, srcFolders, curDestPath, destFolders, destRootPath, remote, trashbin):
        """更新当前文件夹下所有文件夹,仅删除,不涉及文件夹内文件的修改"""
        uselessFolders = destFolders.difference(srcFolders)

        for f in uselessFolders:
            destPath = os.path.join(curDestPath, f)
            trashbin.moveToTrashbin(destPath, destRootPath)
            for r in remote:
                r.rm(destPath[len(destRootPath)+1:])

    def _handleFolder(self, srcPath, destInfo, trace=''):
        """同步当前传入的folderReference"""
        destPath = destInfo['destPath']
        expiredPeriod = destInfo['expiredPeriod']
        lastSyncTime = None if destInfo['lastSyncTime'] is None else parseStrfTime(self.dateTimePattern, destInfo['lastSyncTime'])
        trashbin = TrashManager(self.trashPath, destPath, expiredPeriod)
        remote = [ServerTransporter(remoteConfig) for remoteConfig in destInfo['remote'] ]


        srcQueue = [trace]
        # 循环遍历,不用递归了
        while len(srcQueue) > 0:
            trace = srcQueue.pop()
            # 当前匹配路径
            curSrcPath = os.path.join(srcPath, trace)
            curDestPath = os.path.join(destPath, trace)

            # 文件夹内部文件改变,文件夹的修改时间并不会变,所以以此判断可能会造成漏判
            print(FC.c("check: {}").format(curSrcPath))

            if not os.path.isdir(curDestPath):
                os.makedirs(curDestPath)
                for r in remote:
                    r.mkdir(curDestPath[len(destPath)+1:])
            # 获得源,目标路径文件夹和文件
            srcFolders, srcFiles = getSubfolderAndFiles(curSrcPath)
            destFolders, destFiles = getSubfolderAndFiles(curDestPath)
            # 比对更新当前文件夹下所有文件夹
            self._syncFolders(srcFolders, curDestPath, destFolders, destPath, remote, trashbin)
            # 比对更新当前文件夹下所有文件
            self._syncFiles(curSrcPath, srcFiles, curDestPath, destFiles, lastSyncTime, destPath, remote, trashbin)
            # 进入下个文件夹
            srcQueue.extend([os.path.join(trace, srcF) for srcF in srcFolders])

        # 额外执行命令
        attachCommandRemoteConfigQueue.extend(
            [r.getConfig(log=True) for r in remote if r.attachCommand is not None])
        trashbin.deleteExpiredFiles()

    def _checkSameInReference(self, path, field):
        for idx, ref in enumerate(self.folderRefernece):
            if field == 'src' and ref['src'] == path:
                return idx
            elif field == 'dest':
                if path in [ dest['destPath'] for dest in ref['dest'] ]:
                    return idx
            elif field == 'name' and ref['name'] == path:
                return idx
        return -1

    def _checkAndDeleteFormerPath(self, path):
        """删除修改前(被弃用)的文件夹路径"""
        if not os.path.isdir(path):
            return
        while True:

            print(("是否删除被弃置的文件夹[" + FC.g("{}") + "]?[y/N]").format(path))
            check = input().strip()

            if check == '' or check.upper() == 'N':
                return
            elif check.upper() == 'Y':
                shutil.rmtree(path)

                print(FC.r("文件夹已删除"))
                return

    def _sync_job(self, reference, destIdxes=None):
        if destIdxes is None:
            threads = [Thread(target=self._handleFolder, args=(reference['src'], dest)) for dest in reference['dest']]
        else:
            threads = [Thread(target=self._handleFolder, args=(reference['src'], reference['dest'][idx])) for idx in destIdxes]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def sync(self, name=None, destIndexes=None, n_jobs=4):
        pool = Pool(n_jobs)
        nowTime = getStrfTime(self.dateTimePattern)

        if name is None:
            # 全部更新
            jobs = [pool.apply_async(self._sync_job, args=(fr,)) for fr in self.folderRefernece]
            [j.get() for j in jobs]

            # 更新时间
            for fr in self.folderRefernece:
                for dest in fr['dest']:
                    dest['lastSyncTime'] = nowTime
        else:
            # 单个更新
            syncFolder = [ref for ref in self.folderRefernece if ref['name'] == name]
            # syncFolder = list(filter(lambda ref: ref['name'] == name, self.folderRefernece))
            assert len(syncFolder) > 0, "没有对应的映射"
            syncFolder = syncFolder[0]

            if destIndexes is None:
                self._sync_job(syncFolder)
                for dest in syncFolder['dest']:
                    dest['lastSyncTime'] = nowTime
            else:
                assert all([idx < len(syncFolder['dest']) for idx in destIndexes])
                self._sync_job(syncFolder, destIndexes)
                for idx in destIndexes:
                    syncFolder['dest'][idx]['lastSyncTime'] = nowTime

        # 写回folderRenference
        self._updateFolderReference()
        # 桌面提醒
        self._desktopNotify()
        # 执行额外remote命令
        print("------exec attatch command------")
        jobs = [pool.apply_async(ServerTransporter.execAttachCommand, args=(config, )) for config in attachCommandRemoteConfigQueue]
        [j.get() for j in jobs]

    def showReference(self, reference):
        print(json.dumps(reference, indent=2))

    def addNewReference(self):
        print("请输入备份源文件夹路径:")
        srcPath = input()
        while not os.path.isdir(srcPath):
            print("\n该地址不是有效的文件夹,请输入备份源文件夹路径:")
            srcPath = input()

        # 若源文件夹已被关联, 则直接并入
        idx = self._checkSameInReference(srcPath, 'src')
        if idx >= 0:
            print("该文件夹已被映射, 只添加目标文件夹配置")

        destrefs = []
        while True:
            print(("\n请输入备份目标文件夹根路径\n(留空则用默认路径)[" + FC.y("{}") + "]:").format(self.defaultDestPath))
            destPath = input()
            if destPath.strip() == '':
                destPath = self.defaultDestPath
            if not os.path.isdir(destPath):
                os.makedirs(destPath)

            srcFolderName = os.path.realpath(srcPath).split('/')[-1]
            print(("\n请输入备份目标文件夹名\n(留空则用源文件夹名)[" + FC.y("{}") + "]:").format(srcFolderName))
            destFolderName = input()
            if destFolderName.strip() == '':
                destFolderName = srcFolderName

            while os.path.isdir(os.path.join(destPath, destFolderName)):
                print("\n目标文件夹下已有同名文件夹,换个名字:")
                destFolderName = input()

            destPath = os.path.join(destPath, destFolderName)

            remotes = []
            ipt = input("是否要挂载远端文件夹(和备份文件夹相同修改,但不做检查)?[y/N]").strip().upper()
            while True:
                if ipt == 'Y':
                    remote = ServerTransporter.createAndTest()
                    if remote is not False:
                        remotes.append(remote)
                    else:
                        print("测试连接失败")
                    ipt = input("是否继续或重新添加远程地址?[y/N]").strip().upper()
                else:
                    break


            while True:
                try:
                    expiredPeriod = input(("\n请输入回收站清理过期天数, 留空则默认[" + FC.y("7天") + "]:")).strip()
                    if expiredPeriod == '':
                        expiredPeriod = 7
                        break
                    else:
                        expiredPeriod = int(expiredPeriod)
                        break
                except:
                    continue

            os.makedirs(destPath)
            destrefs.append({
                "destPath": destPath,
                "expiredPeriod": expiredPeriod * 24 * 3600,
                "lastSyncTime": None,
                "remote": remotes
            })

            i = input("是否继续添加目标地址?[y/N]").strip().upper()
            if i != 'Y':
                break

        if idx < 0:
            refname = input("再给这个备份关联起个名字, 留空默认[" + FC.y(srcFolderName) + "]:").strip()
            if refname == '':
                refname = srcFolderName
            while self._checkSameInReference(refname, "name") >= 0:
                refname = input("名字已被占用重新输入, 留空默认[" + FC.y(srcFolderName) + "]:").strip()
                if refname == '':
                    refname = srcFolderName

            reference = {
                "name": refname,
                "src": srcPath,
                "dest": destrefs
            }
            self.folderRefernece.append(reference)
        else:
            self.folderRefernece[idx]['dest'].extend(destrefs)
            reference = self.folderRefernece[idx]

        print(FC.g("添加成功"))
        self.showReference(reference)
        self._updateFolderReference()

    def delRenference(self):
        self.display()

        print(FC.r('请输入要删除的序号:'))
        idx = input()

        try:
            _idx = int(idx)
            assert 0 <= _idx < len(self.folderRefernece), '序号超出范围'

            self._checkAndDeleteFormerPath(self.folderRefernece[_idx]['src'])
            for dest in self.folderRefernece[_idx]['dest']:
                self._checkAndDeleteFormerPath(dest['destPath'])
                self._checkAndDeleteFormerPath(TrashManager.getDestRootPathInTrash(self.trashPath, dest['destPath']))
                for remote in dest['remote']:
                    i = input("确认删除{}吗?[Y/n]".format(remote['username'] + '@' + remote['host'] + ':' + remote['rootPath'])).strip().upper()
                    if i != 'N':
                        try:
                            server = ServerTransporter(remote)
                            server.rm(remote['rootPath'])
                            print("remote文件夹已删除")
                        except:
                            print("删除失败")

            self.folderRefernece.pop(_idx)
            self._updateFolderReference()
            print("文件夹映射更新成功")
        except:
            print('序号不合规范')

    def modifyRenference(self):
        self.display()

        idx = input(FC.r("请输入要修改的序号:"))
        try:
            _idx = int(idx)
            assert _idx < len(self.folderRefernece), '序号超出范围'

            print("\n" + FC.g("[1]") + "修改原路径")
            print(FC.g("[2]") + "修改目标路径")
            modifyField = int(input(FC.c("请输入修改项:")))

            # modifyField = int(input())
            if modifyField == 1:
                # 修改原路径
                print("请输入备份原文件夹路径:")
                srcPath = input()

                while not os.path.isdir(srcPath):
                    print("\n该地址不是有效的文件夹,请输入备份源文件夹路径:")
                    srcPath = input()

                if srcPath == self.folderRefernece[_idx]['src']:
                    print("文件夹未变动")

                assert self._checkSameInReference(srcPath, 'src') < 0, "路径已存在在当前备份中"
                assert self._checkSameInReference(srcPath, 'dest') < 0, "还不支持映射中存在相同的原路径和目标路径"

                self._checkAndDeleteFormerPath(self.folderRefernece[_idx]['src'])
                self.folderRefernece[_idx]['src'] = srcPath
                self._updateFolderReference()
                print("更新完毕")
            else:

                for idx, dest in enumerate(self.folderRefernece[_idx]['dest']):
                    print("\n" + FC.g("[{}]".format(idx)) + dest['destPath'])
                    for remote in dest['remote']:
                        print("     " + remote['username'] + '@' + remote['host'] + ':' + remote['rootPath'])

                _destIdx = int(input("请输入要修改的目标路径编号:"))
                assert 0 <= _destIdx <= idx, "编号有误"

                idx = 0
                dest = self.folderRefernece[_idx]['dest'][_destIdx]
                print("\n" + FC.g("[{}]".format(idx)) + dest['destPath'])
                for remote in dest['remote']:
                    idx += 1
                    print(FC.g("[{}]".format(idx)) + remote['username'] + '@' + remote['host'] + ':' + remote['rootPath'])

                _destIdx = int(input("请输入要修改的目标路径编号:"))
                assert 0 <= _destIdx <= idx, "编号有误"

                if _destIdx == 0:
                    # 修改目标路径
                    _t = True
                    while _t:
                        print("\n请输入备份目标文件夹绝对路径:")
                        destPath = input()
                        if not os.path.isdir(destPath):
                            os.makedirs(destPath)
                            _t = False
                        else:
                            _i = input("该文件夹非空,使用则清空文件夹,确认使用吗?[y/N]")
                            if _i.strip() == '' or _i.strip().upper() == 'N':
                                continue
                            elif _i.upper() == 'Y':
                                _t = False
                            else:
                                print("输入有误")

                    if destPath != dest['destPath']:
                        assert self._checkSameInReference(destPath, 'dest') < 0, "路径已存在在当前备份中"
                        assert self._checkSameInReference(destPath, 'src') < 0, "还不支持映射中存在相同的原路径和目标路径"

                        trashPath = TrashManager.getDestRootPathInTrash(self.trashPath, dest['destPath'])
                        self._checkAndDeleteFormerPath(dest['destPath'])
                        self._checkAndDeleteFormerPath(trashPath)
                        dest['destPath'] = destPath
                        self._updateFolderReference()
                        print("更新完毕")
                    else:
                        print("文件夹未变动")
                        return
                else:
                    # remote
                    print("修改远程配置尚未完成")

        except AssertionError as e:
            print(e)
        except:
            print('序号不合规范')

    def display(self):
        if len(self.folderRefernece) == 0:

            print(FC.w("当前还没有正在备份的文件夹", 'g') + "\n")
        else:
            print(FC.w("当前备份文件夹信息:", 'c') + "\n")
            for idx, ref in enumerate(self.folderRefernece):
                print(FC.g("[{}] {}\n".format(str(idx).zfill(2), ref['name'])) + "     Src: {}".format(ref['src']))
                for destIdx, dest in enumerate(ref['dest']):
                    if dest['lastSyncTime'] is None:
                        print('       {} Dest: {}{}'.format(
                            FC.g("[{}]".format(str(destIdx).zfill(2))),
                            dest['destPath'],
                            FC.y("[尚未备份]")
                        ))
                    else:
                        print('       [{}] Dest: {}{}'.format(
                            FC.g("[{}]".format(str(destIdx).zfill(2))),
                            dest['destPath'],
                            FC.y("[{}]".format(dest['lastSyncTime']))
                        ))

                    for remote in dest['remote']:
                        text = remote['username'] + '@' + remote['host'] + ':' + remote['rootPath']
                        print('            Remote: {}'.format(text))
                    print()


if __name__ == "__main__":
    buu = BackUpUtil()
    buu.sync()
    # buu.delRenference()
