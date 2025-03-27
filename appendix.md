### (Optional)卸载 Python 官网 pkg 方式安装的Python

如果你之前从 Python官网下载了pkg进行安装，我们还需要先卸载这个Python, 以免多个Python引起混乱。

从 www.python.org 下载的 pkg 安装后， 一般会做以下四件事情：

1. 主要文件都安装在 `/Library/Frameworks/Python.framework`
1. 在 `/Applications/Python 2.7` 里创建了两个图标，便于在 Launchpad里搜到， IDEL 和 Python Launcher.
1. 在`/usr/local/bin`下创建一些软链接
1. 修改 shell 的 profile文件，把 python 加入 PATH 环境变量，例如 bash 就是  `~/.bash_profile`, zsh 就是 `~/.zprofile`

卸载步骤：

1. `sudo rm -rf /Library/Frameworks/Python.framework/`
1. `sudo rm -rf "/Applications/Python 2.7"`
1. 删除软链接

        cd /usr/local/bin/
        ls -l /usr/local/bin | grep '../Library/Frameworks/Python.framework/Versions/2.7' | awk '{print $9}' | tr -d @ | xargs rm

1. 删除 shell 的profile文件里的PATH 环境变量

Apple自带的 Python 在 `/System/Library/Frameworks/Python.framework` 和 `/usr/bin/python`，千万不要删除这两个，因为操作系统本身的一些功能依赖Python。

参考：

* [How to uninstall Python 2.7 on Mac OS X - stackoverflow](http://stackoverflow.com/a/3819829/381712)
* [Getting and Installing Macpython](https://docs.python.org/3/using/mac.html#getting-and-installing-macpython)。
