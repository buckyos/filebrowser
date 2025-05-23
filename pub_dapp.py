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

buckycli_path = os.path.join("/opt/buckyos/bin/buckycli", "buckycli")
if platform.system() == "Windows":
    buckycli_path += ".exe"

def get_default_pkg_dir():
    """获取默认的待发布的pack的pkg目录"""
    if platform.system() == "Windows":
        sys_temp_dir = tempfile.gettempdir()
    else:
        sys_temp_dir = "/tmp/"
    return os.path.join(sys_temp_dir, app_name)

def get_default_target_dir():
    """获取默认的输出目录"""
    if platform.system() == "Windows":
        sys_temp_dir = tempfile.gettempdir()
    else:
        sys_temp_dir = "/tmp/"
    target_dir = os.path.join(sys_temp_dir, f"{app_name}_pkg_out")
    os.makedirs(target_dir, exist_ok=True)
    return target_dir

def pack_packages(pkg_dir, target_dir):
    """打包所有有效的包"""
    packed_dirs = []
    
    # 扫描所有包目录
    pkg_dirs = glob.glob(os.path.join(pkg_dir, "*"))
    for pkg_path in pkg_dirs:
        if not os.path.isdir(pkg_path):
            continue
            
        # 检查是否有有效的.pkg_meta.json
        meta_file = os.path.join(pkg_path, ".pkg_meta.json")
        if not os.path.exists(meta_file):
            print(f"跳过 {pkg_path}: 没有找到 .pkg_meta.json")
            continue
            
        try:
            with open(meta_file, 'r') as f:
                meta_data = json.load(f)
                if "pkg_name" not in meta_data or "version" not in meta_data:
                    print(f"跳过 {pkg_path}: .pkg_meta.json 缺少必要字段")
                    continue
                    
            # 调用buckycli pack_pkg命令打包
            
            cmd = [buckycli_path, "pack_pkg", pkg_path, target_dir]
            print(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                pkg_name = os.path.basename(pkg_path)
                packed_dir = os.path.join(target_dir, pkg_name)
                packed_dirs.append(packed_dir)
                print(f"成功打包 {pkg_name}")
            else:
                print(f"打包 {pkg_path} 失败: {result.stderr}")
                
        except Exception as e:
            print(f"处理 {pkg_path} 时出错: {str(e)}")
    
    return packed_dirs

def publish_packages(packed_dirs):
    target_dir = get_default_target_dir()
    cmd = [buckycli_path, "pub_pkg", target_dir]
    print(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("成功发布包")
        return True
    else:
        print(f"发布包失败: {result.stderr}")
        return False
    
def publish_app():
    """发布app到zone内"""
    target_dir = get_default_target_dir()
    cmd = [buckycli_path, "pub_app", "--app_name", app_name,"--target_dir",target_dir]
    print(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("成功发布app")
        return True
    else:
        print(f"发布app失败: {result.stderr}")
        return False
    

def main():
    # 获取默认目录
    pkg_dir = get_default_pkg_dir()
    real_app_doc = json.load(open(f"{pkg_dir}/{app_name}.doc.json"))
    target_dir = get_default_target_dir()
    json.dump(real_app_doc, open(f"{target_dir}/{app_name}.doc.json", "w"))
    
    # 处理命令行参数
    if len(sys.argv) > 1:
        pkg_dir = sys.argv[1]
    if len(sys.argv) > 2:
        target_dir = sys.argv[2]
    
    print(f"使用包目录: {pkg_dir}")
    print(f"使用输出目录: {target_dir}")
    
    if not os.path.exists(pkg_dir):
        print(f"错误: 包目录 {pkg_dir} 不存在")
        return 1
        
    # 打包所有包
    packed_dirs = pack_packages(pkg_dir, target_dir)
    
    # 发布包
    if not publish_packages(packed_dirs):
        print("发布包失败")
        return 1
    
    if not publish_app():
        print("发布app失败")
        return 1

    print("所有操作完成")
    return 0

if __name__ == "__main__":
    sys.exit(main())
