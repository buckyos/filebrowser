
## 标准的应用开发环境
#确认repo-server已配置成开发模式（git clone的版本默认就是开发环境）
#构建时要注意app sub pkg-name必须是完整版的：nightly-apple-x86_64.$pkg_name#version

### 构建 （TODO：app 标准开发目录，考虑到全平台编译工具的完善，默认使用linux，windows和osx平台需要用户手工build好复制到target目录)
#1. 构建全平台2进制 --> 构建对应的Docker
#2. 基于docker image 构建全平台的image sub_pkg
#3. 如果是系统应用，还需要基于二进制再构建全平台的bin sub_pkg
#为了提高效率，在测试阶段可以只针对开发环境构建一个平台的pkg

### 测试
#1. 注意更新app_name.app_doc.json 的版本
#2. 使用buckycli pub_app 将app发布到zone内
#3. 使用buckycli pub_index 使发布在zone内生效
#   4.1 使用buckycli 在zone内安装应用（如已安装可逃过）
#   4.2 zone内已经运行的app会变成新版本

### 发布
#根据不同的source-service的规则，提交新的app_doc.
#发布的时候有2个channel (nightly / release),这两个环境是独立的。 不依赖nightly新功能的应用开发者，只需要基于release channel进行构建和发布就好了。
#在提交app_doc之前，应确保已经获得了 可提交资格（已认证开发者)


# ------------------
#1. 构建当前能构建的的bin docker img(并导出为tar文件)
#2. 复制到特定的pkg目录，并准备合适的.pkg.meta.json文件(该文件也是由脚本产生)
#3. 使用buckycli pub_pkg 发布pkg到zone内
#3. 使用buckycli publish_app 发布app到zone内
#4. 使用buckycli pub_index 使发布在zone内生效
import os;
import subprocess;
import tempfile;
import platform;

platform_name = platform.system().lower()
if platform_name == "windows":
    sys_temp_dir = tempfile.gettempdir()
else:
    sys_temp_dir = "/tmp/"

output_dir = os.path.join(sys_temp_dir, "filebrowser");
version = "0.4.0";
print("OUTPUT: ", output_dir);

def create_output_dir(dir_path):
    subprocess.run(["rm", "-rf", dir_path]);
    subprocess.run(["mkdir", "-p", dir_path]);
    return dir_path;

def build_web_pages():
    subprocess.run(["make", "build-frontend"]);

def build_app(app_name,os_name, arch_name):
    # 设置构建环境变量
    env = os.environ.copy()
    env["GOOS"] = os_name
    env["GOARCH"] = arch_name
    subprocess.run(["make", "build-backend"], env=env)

    if os_name == "linux":
        pkg_id = f"nightly-{os_name}-{arch_name}.buckyos-{app_name}-img";
        sub_pkg_dir = os.path.join(output_dir, pkg_id);
        create_output_dir(sub_pkg_dir);
        subprocess.run(["docker", "buildx", "build", "--platform", f"linux/{arch_name}", "-t", f"buckyos-nightly/{app_name}:{version}-{arch_name}","."]);
        # 获取Docker镜像的hash
        image_name = f"buckyos-nightly/{app_name}:{version}-{arch_name}"
        image_hash = subprocess.check_output(["docker", "images", "--no-trunc", "-q", image_name]).decode().strip()
        print(f"Docker image hash for {image_name}: {image_hash}")
    
        # 导出Docker镜像为tar文件
        tar_file_path = os.path.join(sub_pkg_dir, f"{app_name}.tar")
        subprocess.run(["docker", "save", "-o", tar_file_path, image_name])
        print(f"Docker image exported to: {tar_file_path}")
    
        # 复制必要的元数据文件到包目录
        subprocess.run(["cp", "publish/docker_pkg.meta.json", sub_pkg_dir])

    if os_name == "windows":
        pkg_id = f"nightly-{os_name}-{arch_name}.buckyos-{app_name}-bin";
        sub_pkg_dir = os.path.join(output_dir, pkg_id);
        create_output_dir(sub_pkg_dir);
        os.rename("filebrowser.exe", os.path.join(sub_pkg_dir, f"filebrowser.exe"));
    
    if os_name == "darwin":
        pkg_id = f"nightly-apple-{arch_name}.buckyos-{app_name}-bin";
        sub_pkg_dir = os.path.join(output_dir, pkg_id);
        create_output_dir(sub_pkg_dir);
        os.rename("filebrowser", os.path.join(sub_pkg_dir, f"filebrowser"));

def main():
    #build_web_pages();
    create_output_dir(output_dir);
    build_app("filebrowser", "linux", "amd64");
    build_app("filebrowser", "linux", "arm64");
    build_app("filebrowser", "windows", "amd64");
    build_app("filebrowser", "darwin", "amd64");
    build_app("filebrowser", "darwin", "arm64");

if __name__ == "__main__":
    main();


