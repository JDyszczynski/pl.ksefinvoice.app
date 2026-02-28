import os
import re
import sys
import shutil
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path

# Configuration
URL_BASE_FLATPAK = "https://www.ksefinvoice.pl/KSEF/Flatpak"
URL_BASE_APPIMAGE = "https://www.ksefinvoice.pl/KSEF/Linux"
URL_BASE_WIN = "https://www.ksefinvoice.pl/KSEF/win"

def get_version(project_root):
    main_qt_path = project_root / "main_qt.py"
    if not main_qt_path.exists():
        print(f"Error: {main_qt_path} not found.")
        sys.exit(1)
    
    with open(main_qt_path, 'r', encoding='utf-8') as f:
        content = f.read()
        match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', content)
        if match:
            return match.group(1)
    return "1.0.0"

def calculate_sha256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def clean_release_dir(release_dir):
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)

def create_zip_archive(source_dir, output_path):
    print(f"Creating ZIP archive: {output_path}...")
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # Archive name relative to source_dir
                arcname = os.path.relpath(file_path, source_dir.parent)
                zipf.write(file_path, arcname)
    print("ZIP created.")

def create_tar_archive(source_dir, output_path):
    print(f"Creating TAR.GZ archive: {output_path}...")
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name)
    print("TAR.GZ created.")

def process_windows(project_root, binary_root, version):
    # binary_root passed as DEPLOY_ROOT
    win_deploy_root = binary_root / "win"
    
    # We want the output in DEPLOY/win essentially.
    # But usually build.bat/pyinstaller puts stuff in DEPLOY/win/dist/KsefInvoice
    
    dist_dir = win_deploy_root / "dist" / "KsefInvoice"
    if not dist_dir.exists():
        print(f"Error: Windows build directory {dist_dir} not found. Run build first.")
        # We don't exit here strictly, maybe just warn, but usually we need dist
        sys.exit(1)

    # User request: "w nim po starem dostane plik programu i podkatalog z zależnościami (nie spakowane) bez pliku version"
    # So we essentially just ensure files are in DEPLOY/win (or kept in dist) and we DO NOT create version.txt
    # and DO NOT create zip if he doesn't want it (though 'prepare_release' implies packaging).
    #
    # However, usually release preparation implies packaging.
    # If the user says "bez pliku version bo go mam już z builda appimage", 
    # it implies he will take version.txt from Linux build.
    
    # Let's clean up old artifacts if any, but keep the raw build?
    # Actually, if PyInstaller runs to DEPLOY/win/dist/KsefInvoice, the files are there.
    # Maybe we just print where they are and skip zipping/version.txt if that's what is requested.
    
    # Let's assume we still want a Zip for the server, but maybe putting it in a specific place?
    # "jak zrobie pod windowsem ... dostane plik programu i podkatalog z zależnościami (nie spakowane)"
    # This sounds like standard PyInstaller directly to DEPLOY/win/KsefInvoice?
    
    # Let's skip modifying process_windows too much aside from path correction (binary_root=DEPLOY)
    # and commenting out version.txt creation as requested.
    
    release_dir = win_deploy_root / "release"
    clean_release_dir(release_dir)

    # 1. Version.txt - SKIP per user request
    # version_file = release_dir / "version.txt"
    # with open(version_file, "w") as f:
    #     f.write(version)
    # print(f"Created {version_file}")

    # 2. Zip Archive (User said "nie spakowane"? Or "w nim ... dostane ... nie spakowane" refering to the build output folder?)
    # Usually users want a ZIP for download from website.
    # "dostane plik programu i podkatalog z zależnościami (nie spakowane)" likely refers to the folder structure he copies to Windows machine?
    # No, he says "jak zrobie pod windowsem ... w nim ... dostane".
    #
    # If I zip it, it's fine for release. If he wants raw files, they are in dist_dir.
    # I will still generate the ZIP in 'release/' because that's for the website (URL_BASE_WIN).
    # But I won't verify/touch the raw files other than reading them.
    
    zip_name = f"KsefInvoice_Win_v{version.replace(' ', '_').replace('(', '').replace(')', '')}.zip"
    zip_path = release_dir / zip_name
    create_zip_archive(dist_dir, zip_path)

    print("\n[WINDOWS RELEASE READY]")
    print(f"Release Zip: {zip_path}")
    print(f"Raw files (unpacked) remain in: {dist_dir}")

def process_linux(project_root, binary_root, version, workspace_root=None):
    # binary_root is passed as DEPLOY_ROOT (e.g., .../KsefInvoice/DEPLOY)
    linux_deploy_root = binary_root / "linux"
    
    # If workspace_root is not provided, try to infer
    if not workspace_root:
        workspace_root = project_root.parent
    
    # User requested structure:
    # DEPLOY/linux/AppImage/ <-- .AppImage file here
    # DEPLOY/linux/Flatpak/  <-- .tar.gz, .json, wrapper, version.txt here

    flatpak_dir = linux_deploy_root / "Flatpak"
    appimage_dir = linux_deploy_root / "AppImage"
    
    # We use flatpak_dir as the release dir for server files
    release_dir = flatpak_dir
    # clean_release_dir(release_dir) # Don't clean, build.sh pre-populated it with wrapper/json/dist
    
    # Input dist for packaging (prepared by build.sh)
    dist_dir = flatpak_dir / "dist" / "KsefInvoice"
    
    if not dist_dir.exists():
        print(f"Error: Linux dist directory {dist_dir} not found. Build process failed?")
        sys.exit(1)

    # 1. Version.txt (goes to Flatpak folder for server upload)
    version_file = release_dir / "version.txt"
    with open(version_file, "w") as f:
        f.write(version)
    print(f"Created {version_file}")

    # 2. AppImage (Handling rename if needed)
    # create_appimage puts it in appimage_dir directly
    if appimage_dir.exists():
        # Find generated AppImage
        found_ai = list(appimage_dir.glob("*.AppImage"))
        if found_ai:
            src = found_ai[0]
            # Rename if needed (build.sh names it KsefInvoice-Linux-x86_64.AppImage)
            # We want versioned name
            new_name = f"KsefInvoice_Linux_v{version.replace(' ', '_').replace('(', '').replace(')', '')}.AppImage"
            dst = appimage_dir / new_name
            if src != dst:
                shutil.move(src, dst)
                print(f"Renamed AppImage to {dst.name}")
        else:
             print("Warning: No AppImage found in AppImage dir.")
    else:
        print("Warning: AppImage directory not found.")



    # 3. Flatpak Source Archive
    
    # 3a. Clean old .tar.gz archives
    for old_file in release_dir.glob("*.tar.gz"):
        try:
             old_file.unlink()
             print(f"Removed old archive: {old_file.name}")
        except Exception as e:
             print(f"Failed to remove {old_file.name}: {e}")

    # Use strict version number for filename (e.g. 1.0.4 from '1.0.4 (Beta)')
    clean_version = version.split(' ')[0]
    
    tar_name = f"KsefInvoice-{clean_version}.tar.gz"
    tar_path = release_dir / tar_name
    create_tar_archive(dist_dir, tar_path)
    
    # Calculate Hash
    sha256 = calculate_sha256(tar_path)
    print(f"Archive SHA256: {sha256}")

    # 3b. Wrapper Script
    # build.sh copies it to flatpak_dir/ksef_wrapper.sh
    wrapper_dst = flatpak_dir / "ksef_wrapper.sh"
    wrapper_sha256 = ""
    
    if wrapper_dst.exists():
        wrapper_sha256 = calculate_sha256(wrapper_dst)
        print(f"Found wrapper script: {wrapper_dst.name}")
        print(f"Wrapper SHA256: {wrapper_sha256}")
    else:
        print("Warning: ksef_wrapper.sh not found in Flatpak dir.")

    # 4. Generate Flatpak Manifest using FlatHub template, but update it IN PLACE in FlatHub folder
    # NOTE: The user requested to update files in FlatHub directory directly.
    # The 'manifest_dst' should be the file in FlatHub, not in DEPLOY.
    template_path = workspace_root / "FlatHub" / "pl.ksefinvoice.KsefInvoice.json"
    manifest_dst = template_path # We update the source file directly!
    
    print(f"Updating FlatHub Manifest at: {manifest_dst}")
    
    if template_path.exists():
        with open(template_path, 'r') as f:
            manifest_data = json.load(f)
        
        # Modify sources
        for module in manifest_data.get("modules", []):
            if isinstance(module, dict):
                # KSEF BINARY
                if module.get("name") == "ksef-binary":
                    # Update build-commands to handle extracted tarball structure
                    
                    found_archive = False
                    for source in module.get("sources", []):
                        if source.get("type") == "archive":
                            # Update URL and SHA256
                            old_url = source.get("url", "")
                            if "KsefInvoice-" in old_url:
                                # Replace filename at end of URL
                                base_url = old_url.rsplit('/', 1)[0]
                                # Attempt to regex replace version in URL
                                new_url = re.sub(r'v\d+\.\d+\.\d+', f'v{clean_version}', old_url)
                                new_url = re.sub(r'KsefInvoice-[\d\.]+\.tar\.gz', tar_name, new_url)
                                source["url"] = new_url
                            else:
                                source["url"] = f"{URL_BASE_FLATPAK}/{tar_name}"
                            
                            source["sha256"] = sha256
                            print(f"Updated archive source to: {source['url']}")
                            found_archive = True
                    
                    if not found_archive:
                         print("Warning: No archive source found in ksef-binary module.")
                
                # LAUNCHER (WRAPPER)
                elif module.get("name") == "launcher" and wrapper_sha256:
                    for source in module.get("sources", []):
                         if source.get("type") == "file" and source.get("dest-filename") == "ksef_wrapper.sh":
                             if "url" in source: # Only update remote wrapper references
                                  source["sha256"] = wrapper_sha256
                                  # If wrapper URL needs versioning, handle it. Usually it's static name.
                             # If it is 'path', it remains local path 'ksef_wrapper.sh', SHA not needed in manifest for simple 'path' usually?
                             # Flatpak builder checks local file. But for FlatHub, wrapper is usually committed repo file.
                             # So we don't update SHA for 'path' type in manifest, we just ensure the file is there (which it is).
                             pass

        with open(manifest_dst, 'w') as f:
            json.dump(manifest_data, f, indent=4)
        print(f"Updated Release Manifest: {manifest_dst.name}")
    else:
        print(f"Warning: Template {template_path} not found.")

    # 5. Update Metainfo.xml in FlatHub
    metainfo_path = workspace_root / "FlatHub" / "pl.ksefinvoice.KsefInvoice.metainfo.xml"
    if metainfo_path.exists():
        update_metainfo(metainfo_path, clean_version)
    else:
        print(f"Warning: Metainfo not found at {metainfo_path}")

    print("\n[LINUX RELEASE READY]")
    print(f"Deploy Root: {linux_deploy_root}")
    print(f"  > AppImage/ (contains executable for website)")
    print(f"  > Flatpak/  (contains tar.gz for Release)")
    print(f"  > FlatHub/  (contains updated Manifest and Metainfo)")

def update_metainfo(path, new_version):
    from datetime import date
    try:
        today_date = date.today().isoformat()
    except Exception as e:
        print(f"Error getting date: {e}")
        today_date = "2026-02-27"

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if this version already exists
    if f'version=\"{new_version}\"' in content:
        print(f"Metainfo already contains version {new_version}")
        return

    # Find <releases> tag
    if "<releases>" in content:
        # Insert new release at the top of releases
        new_release_tag = f'    <release version="{new_version}" date="{today_date}" />'
        
        # Use simple replace for first occurrence
        content = content.replace("<releases>", f"<releases>\n{new_release_tag}")
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated Metainfo with version {new_version} and date {today_date}")
    else:
        print("Warning: <releases> tag not found in metainfo.xml")

def main():
    if len(sys.argv) < 2:
        print("Usage: python prepare_release.py [win|linux]")
        sys.exit(1)
        
    platform_mode = sys.argv[1]
    
    # Determine paths
    # This script is in /.../PRODUKCYJNA/Binary/prepare_release.py
    # Project Root is ../..
    script_path = Path(__file__).resolve()
    binary_root = script_path.parent
    project_root = binary_root.parent
    
    print(f"Project Root: {project_root}")
    version = get_version(project_root)
    print(f"Detected Version: {version}")
    
    if platform_mode == "win":
        process_windows(project_root, binary_root, version)
    elif platform_mode == "linux":
        process_linux(project_root, binary_root, version)
    else:
        print("Unknown platform")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python prepare_release.py [win|linux] [optional_deploy_root]")
        sys.exit(1)
        
    platform_mode = sys.argv[1]
    
    # Determine paths
    script_path = Path(__file__).resolve()
    
    # Default binary_root (if not provided)
    # usually .../PRODUKCYJNA/Binary
    binary_root = script_path.parent
    project_root = binary_root.parent

    # If argument provided, use it as ROOT for deployment (PROJECT/DEPLOY_ROOT)
    # NOTE: The script logic uses 'binary_root' variable as the base for 'linux' or 'win' folders.
    # checking argv[2]
    if len(sys.argv) >= 3:
        candidate = Path(sys.argv[2])
        if candidate.is_absolute():
             binary_root = candidate
        else:
             binary_root = Path(os.getcwd()) / candidate
        print(f"Using Custom Deploy Root: {binary_root}")
        # Recalculate workspace_root based on DEPLOY root (DEPLOY is in workspace root)
        workspace_root = binary_root.parent
    else:
        # Assume we are in ENV/Binary
        # So workspace_root is ENV/..
        workspace_root = project_root.parent

    print(f"Project Root (for version check): {project_root}")
    print(f"Workspace Root (for templates): {workspace_root}")
    
    version = get_version(project_root)
    print(f"Detected Version: {version}")
    
    if platform_mode == "win":
        process_windows(project_root, binary_root, version)
    elif platform_mode == "linux":
        # Pass workspace_root so it can find FlatHub
        process_linux(project_root, binary_root, version, workspace_root)
    else:
        print("Unknown platform")
