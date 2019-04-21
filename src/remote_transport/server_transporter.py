import paramiko
import time
import os
import json

from src.font_color import font_color as FC

###
# config = {
#     "host": "47.107.90.226",
#     "port": 22,
#     "username": "root",
#     "pwd": null,
#     "privateKeyPath": "/home/mopip77/.ssh/id_rsa",
#     "rootPath": "/var/www/html/notebook",
#     "syncReference": 0
#}

class ServerTransporter():
    def __init__(self, config):
        self.host = config['host']
        self.port = config['port']
        self.username = config['username']
        self.pwd = config['pwd']
        self.privateKeyPath = config['privateKeyPath']
        self.rootPath = config['rootPath']
        self.attachCommand = None if 'attachCommand' not in config.keys() else config['attachCommand']
        self.transLog = {
            'update': [],
            'delete': []
        }

        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        transport = paramiko.Transport((self.host, self.port))
        if self.pwd is not None:
            self._ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.pwd)
            transport.connect(username=self.username, password=self.pwd)
        else:
            self._ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                key_filename=self.privateKeyPath)
            private_key = paramiko.RSAKey.from_private_key_file(self.privateKeyPath)
            transport.connect(username=self.username, pkey=private_key)

        self._sftp = paramiko.SFTPClient.from_transport(transport)
    
    def put(self, srcPath, relativeDestPath):
        destPath = os.path.join(self.rootPath, relativeDestPath)
        try:
            self._sftp.put(srcPath, destPath)
            self.transLog['update'].append(destPath)
        except:
            # 可能是没有相应的文件夹结构
            folderPath = '/'.join(destPath.split('/')[:-1])
            stdin, stdout, stderr = self._ssh.exec_command("mkdir -p " + folderPath)
            err = stderr.read().decode('utf8')
            if err == "":
                self._sftp.put(srcPath, destPath)
                self.transLog['update'].append(destPath)
            else:
                # 文件夹不可创建
                print(err)

    def mkdir(self, relativePath):
        path = os.path.join(self.rootPath, relativePath)
        stdin, stdout, stderr = self._ssh.exec_command("ls " + path)
        err = stderr.read().decode('utf8')
        if err == '':
            # 多线程不能输入, 暂且不确认
            self.rm(path)
            # ipt = input("该文件夹已存在,是否清空?[y/N]").strip().upper()
            # if ipt == 'Y':
            #     if self.rm(path) is False:
            #         return False
            # else:
            #     return False

        stdin, stdout, stderr = self._ssh.exec_command("mkdir -p " + path)
        err = stderr.read().decode('utf8')
        return err == ""


    def rm(self, relativePath):
        destPath = os.path.join(self.rootPath, relativePath)
        stdin, stdout, stderr = self._ssh.exec_command("rm -rf " + destPath)
        err = stderr.read().decode('utf8')
        if err != '':
            print("文件夹删除失败")
            return False
        else:
            self.transLog['delete'].append(destPath)
            return True

    def getConfig(self, log=None):
        config = {}
        config['host'] = self.host
        config['port'] = self.port
        config['username'] = self.username
        config['pwd'] = self.pwd
        config['privateKeyPath'] = self.privateKeyPath
        config['rootPath'] = self.rootPath
        config['attachCommand'] = self.attachCommand
        if log is not None:
            config['transLog'] = self.transLog
        print(self.transLog)
        print(config)
        return config

    def __str__(self):
        return self.username + '@' + self.host + ':' + self.rootPath

    @staticmethod
    def execAttachCommand(config):
        remoteLogFile = "/tmp/" + '_'.join(config['rootPath'].split('/'))
        fp = open(remoteLogFile, 'w')
        fp.write(json.dumps(config['transLog']))
        fp.close()

        remote = ServerTransporter(config)
        remote.put(remoteLogFile, remoteLogFile)
        if remote.attachCommand is not None:
            print(FC.g("[Do] ") + remote.username + '@' + remote.host + ':' + remote.rootPath + ' => ' + remote.attachCommand)
            stdin, stdout, stderr = remote._ssh.exec_command(remote.attachCommand)
            # 阻塞等待
            err = stderr.read()

    @staticmethod
    def createAndTest():
        config = {}
        config['host'] = input("域名:")
        config['port'] = int(input("端口:"))
        config['username'] = input("用户名:")
        config['pwd'] = input("密码(留空则用秘钥文件登陆):").strip()
        if config['pwd'] == '':
            config['pwd'] = None
            config['privateKeyPath'] = input("请输入秘钥文件路径:")
        else:
            config['privateKeyPath'] = None
        config['rootPath'] = input("远端备份路径:")

        try:
            server = ServerTransporter(config)
            print(FC.g("测试连接成功"))
            while not server.mkdir(''):
                config['rootPath'] = input("请重新输入远程路径:")
            return config
        except:
            return False


if __name__ == "__main__":
    print('errLogPath')