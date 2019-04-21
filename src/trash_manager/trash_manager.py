import os
import time
import shutil

from src.font_color import font_color as FC
from src.utils.myfile import getSubfolderAndFiles, fileLastModifyTime
from src.utils.mytime import getStrfTime


class TrashManager():

    DATETIME_PATTERN = "%Y-%m-%d_%H:%M:%S"

    def __init__(self, trashRootPath, destRootPath, expiredPeriod):
        self.rootPath = self.getDestRootPathInTrash(trashRootPath, destRootPath)
        if not os.path.isdir(self.rootPath):
            os.makedirs(self.rootPath)
        self.expireTime = time.time() - expiredPeriod

    def deleteExpiredFiles(self):
        """从rootPath开始后序遍历的生成器, 返回(当前路径p,p中所有文件夹名,p中所有文件名)"""
        # [路径, 是否被添加过], 后序遍历防止重复添加
        stack = [[self.rootPath, False]]
        while len(stack):
            curFolderPath, visited = stack[-1]
            folders, files = getSubfolderAndFiles(curFolderPath)
            
            if visited is False and len(folders):
                stack[-1][1] = True
                stack += [[path, False] for path in [os.path.join(curFolderPath, f) for f in list(folders)] ]
            else:
                for f in files:
                    self._checkAndDeleteExpiredFile(os.path.join(curFolderPath, f))
            
                remainItems = os.listdir(curFolderPath)
                # rootPath 不能删除
                if curFolderPath != self.rootPath and len(remainItems) == 0:
                    shutil.rmtree(curFolderPath)
                
                stack.pop()

    def _checkAndDeleteExpiredFile(self, filePath):
        if fileLastModifyTime(filePath) < self.expireTime:
            os.remove(filePath)

    def moveToTrashbin(self, srcPath, srcRootPath):
        assert os.path.exists(srcPath), "被移动文件不存在"
        
        relativePath = srcPath[len(srcRootPath)+1:]
        path = os.path.join(self.rootPath, relativePath)
        l = path.split('/')
        folderPath = '/'.join(l[:-1])
        filename = l[-1]

        if os.path.exists(path):
            shutil.move(srcPath, "{}/{}_{}".format(folderPath, getStrfTime(self.DATETIME_PATTERN), filename))
        else:
            if not os.path.exists(folderPath):
                os.makedirs(folderPath)
            shutil.move(srcPath, path)
        
        print(FC.r("<Trash> ") + path)

    @staticmethod
    def getDestRootPathInTrash(trashRootPath, srcRootPath):
        return os.path.join(
                trashRootPath,
                '_'.join(srcRootPath.split('/')) 
                )

if __name__ == "__main__":
    a = TrashManager("/home/mopip77/Desktop/univercity/MintBackup/_cycle_")
    a.deleteExpiredFiles()

        