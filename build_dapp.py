

import os;
import subprocess;
import tempfile;
import platform;
import json;
import time;
import sys;
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
platform_name = platform.system().lower()
if platform_name == "windows":
    sys_temp_dir = tempfile.gettempdir()
else:
    sys_temp_dir = "/tmp/"

output_dir = os.path.join(app_raw_dir, app_name, version);
print("OUTPUT: ", output_dir);
all_images = [];

def process_pkg_meta(pkg_meta_path,new_path,pkg_name):
    pkg_meta = json.load(open(pkg_meta_path));
    pkg_meta["pub_time"] = int(time.time())
    pkg_meta["exp"] = int(time.time()) + 3600 * 24 * 365 * 3
    pkg_meta["pkg_name"] = pkg_name 
    json.dump(pkg_meta, open(new_path, "w"));
    return pkg_meta;


def create_output_dir(dir_path):
    subprocess.run(["rm", "-rf", dir_path]);
    subprocess.run(["mkdir", "-p", dir_path]);
    return dir_path;

def build_web_pages():
    result = subprocess.run(["make", "build-frontend"])
    if result.returncode != 0:
        print("构建前端失败")
        sys.exit(1)

def build_app(os_name, arch_name):
    # 设置构建环境变量
    docker_file = "./Dockerfile.s6"
    env = os.environ.copy()
    env["GOOS"] = os_name
    env["CGO_ENABLED"] = "0"
    if arch_name == "aarch64":
        env["GOARCH"] = "arm64"
        docker_file = "./Dockerfile.s6.aarch64"
    else:
        env["GOARCH"] = arch_name
    
    result = subprocess.run(["make", "build-backend"], env=env)
    if result.returncode != 0:
        print(f"构建后端失败: {os_name}-{arch_name}")
        sys.exit(1)

    if os_name == "linux":
        pkg_id = f"nightly-{os_name}-{arch_name}.{app_name}-img";
        sub_pkg_dir = os.path.join(output_dir, pkg_id);
        create_output_dir(sub_pkg_dir);
        pkg_meta = process_pkg_meta("./publish/docker_pkg_meta.json", f"{sub_pkg_dir}/pkg_meta.json", pkg_id);
        pkg_version = pkg_meta["version"];
        image_name = f"{docker_username}/nightly-{app_name}:{pkg_version}-{arch_name}"
        result = subprocess.run(["docker", "buildx", "build", "--platform", f"linux/{arch_name}", "-t", image_name, "-f",docker_file,"."])
        if result.returncode != 0:
            print(f"Docker构建失败: {os_name}-{arch_name}")
            sys.exit(1)

        # 获取Docker镜像的hash
        image_hash = subprocess.check_output(["docker", "images", "--no-trunc", "-q", image_name]).decode().strip()
        print(f"Docker image hash for {image_name}: {image_hash}")
    
        # 导出Docker镜像为tar文件
        tar_file_path = os.path.join(sub_pkg_dir, f"{app_name}.tar")
        result = subprocess.run(["docker", "save", "-o", tar_file_path, image_name])
        
        if result.returncode != 0:
            print(f"Docker镜像导出失败: {image_name}")
            sys.exit(1)
        print(f"Docker image exported to: {tar_file_path}")
        all_images.append(image_name);
    
        # 复制必要的元数据文件到包目录

        app_doc["pkg_list"][f"{arch_name}_docker_image"]["pkg_id"] = f"{pkg_id}";
        app_doc["pkg_list"][f"{arch_name}_docker_image"]["docker_image_name"] = f"buckyos/nightly-{app_name}:{version}-{arch_name}"
        #app_doc["pkg_list"][f"{arch_name}_docker_image"]["docker_image_hash"] = image_hash;
        app_doc["deps"][pkg_id] = pkg_version

    if os_name == "windows":
        pkg_id = f"nightly-{os_name}-{arch_name}.{app_name}-bin";
        sub_pkg_dir = os.path.join(output_dir, pkg_id);
        create_output_dir(sub_pkg_dir);
        #复制./publish/app_pkg/的所有文件到sub_pkg_dir
        os.system(f"cp ./publish/app_pkg/* {sub_pkg_dir}")
        pkg_meta = process_pkg_meta("./publish/app_pkg/pkg_meta.json", f"{sub_pkg_dir}/pkg_meta.json", pkg_id);
        pkg_version = pkg_meta["version"];
        print(pkg_meta);

        os.rename("filebrowser.exe", os.path.join(sub_pkg_dir, f"filebrowser.exe"));

        app_doc["pkg_list"][f"{arch_name}_win_app"]["pkg_id"] = f"{pkg_id}";
        app_doc["deps"][pkg_id] = pkg_version
     
    if os_name == "darwin":
        pkg_id = f"nightly-apple-{arch_name}.{app_name}-bin";
        sub_pkg_dir = os.path.join(output_dir, pkg_id);
        create_output_dir(sub_pkg_dir);
        os.system(f"cp ./publish/app_pkg/* {sub_pkg_dir}")
        pkg_meta = process_pkg_meta("./publish/app_pkg/pkg_meta.json", f"{sub_pkg_dir}/pkg_meta.json", pkg_id);
        pkg_version = pkg_meta["version"];
        print(pkg_meta);

        os.rename("filebrowser", os.path.join(sub_pkg_dir, f"filebrowser"));

        app_doc["pkg_list"][f"{arch_name}_apple_app"]["pkg_id"] = f"{pkg_id}";
        app_doc["deps"][pkg_id] = pkg_version
    


def main():
    build_web_pages();

    create_output_dir(output_dir);
    app_doc["deps"] = {};

    build_app("linux", "amd64");
    print("#=> linux amd64 build done");
    build_app("linux", "aarch64");
    print("#=> linux aarch64 build done");

    if is_system_app:
        build_app("windows", "amd64");
        print("#=> windows amd64 build done");
        build_app("darwin", "amd64");
        print("#=> darwin amd64 build done");
        build_app("darwin", "aarch64");
        print("#=> darwin aarch64 build done");
    
    app_doc["pub_time"] = int(time.time())
    app_doc["exp"] = int(time.time()) + 3600 * 24 * 365 * 3
    json.dump(app_doc, open(f"{output_dir}/app.doc.json", "w"));
    print(f"packed app_doc: {app_doc}");
    print("\n--------------------------------");
    print("^ ^ all build done ^ ^, output dir: ", output_dir);
    for image in all_images:
        print(f"  - create docker image: {image}");
    # 使用buckycli pub_pkg 发布pkg到zone内
if __name__ == "__main__":
    main();


