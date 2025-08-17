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

def get_default_target_dir():
    os.makedirs(build_target_dir, exist_ok=True)
    return build_target_dir

def pack_packages(input_dir, target_dir):
    """打包所有有效的包"""
    packed_dirs = []
    
    # 扫描所有包目录
    pkg_dirs = glob.glob(os.path.join(input_dir, "*"))
    for pkg_path in pkg_dirs:
        if not os.path.isdir(pkg_path):
            continue
            
        # 检查是否有有效的pkg_meta.json
        meta_file = os.path.join(pkg_path, "pkg_meta.json")
        if not os.path.exists(meta_file):
            print(f"跳过 {pkg_path}: 没有找到 pkg_meta.json")
            continue
            
        try:
            with open(meta_file, 'r') as f:
                meta_data = json.load(f)
                if "pkg_name" not in meta_data or "version" not in meta_data:
                    print(f"跳过 {pkg_path}: pkg_meta.json 缺少必要字段")
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

    

def main():
    # 获取build结果目录
    target_dir = get_default_target_dir()
    real_app_doc = json.load(open(f"{target_dir}/{app_name}.doc.json"))
    # 获取打包后的pkg目录 
    pkg_dir = get_default_pkg_dir()
    
    print(f"build target dir: {target_dir}")
    print(f"publish pkg dir: {pkg_dir}")

    
    if not os.path.exists(target_dir):
        print(f"!!! build target dir {target_dir} 不存在")
        return 1
        
    # 打包所有包
    packed_dirs = pack_packages(target_dir, pkg_dir)
    

    print("Done. Packed pkg dirs: ", packed_dirs);
    return 0

if __name__ == "__main__":
    sys.exit(main())
