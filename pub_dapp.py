import os
import glob
import subprocess
import tempfile
import platform
import sys
import json

########################################################
# 根据需要修改下面3个
app_doc = json.load(open("./publish/app.doc.json"));
is_system_app = True;
docker_username = "buckyos";
########################################################
print("APP_DOC: ", app_doc);
version = app_doc["version"];
app_name = app_doc["pkg_name"];
app_base_dir = "/opt/buckyosci/apps/"
app_raw_dir = "/opt/buckyosci/app_build/"
build_target_dir = os.path.join(app_raw_dir, app_name, version);
app_pkg_dir = os.path.join(app_base_dir, app_name, version);

buckycli_path = os.path.join("/opt/buckyos/bin/buckycli", "buckycli")
if platform.system() == "Windows":
    buckycli_path += ".exe"

def get_default_pkg_dir():
    return app_pkg_dir;

def publish_packages(packed_dirs):
    """发布app的所有sub pkg到zone内"""
    cmd = [buckycli_path, "pub_pkg", packed_dirs]
    print(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("成功发布包")
        return True
    else:
        print(f"发布包失败: {result.stderr}")
        return False
    
def publish_app(packed_dirs):
    """发布app到zone内"""
    cmd = [buckycli_path, "pub_app","--target_dir",packed_dirs]
    print(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("成功发布app")
        return True
    else:
        print(f"发布app失败: {result.stderr}")
        return False
    

def main():
    # 获取打包后的pkg目录 
    pkg_dir = get_default_pkg_dir()

    if not os.path.exists(pkg_dir):
        print(f"!!! packed dapp  dir {pkg_dir} 不存在")
        return 1
    
    if not publish_app():
       print("发布app失败")
       return 1

    print("所有操作完成")
    return 0

if __name__ == "__main__":
    sys.exit(main())
