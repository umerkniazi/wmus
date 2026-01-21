import os
import sys
import shutil
import subprocess

VERSION = "1.0.0"

def remove_old_builds():
    folders = ['build', 'dist', 'installer_files']
    for folder in folders:
        if os.path.exists(folder):
            print(f"Cleaning {folder}/")
            shutil.rmtree(folder)
    
    if os.path.exists('wmus.spec'):
        os.remove('wmus.spec')

def build_executable():
    print("\n=== Building wmus.exe ===\n")
    
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        'main.py',
        '--name=wmus',
        '--onefile',
        '--console',
        '--add-data=config.json;.',
        '--hidden-import=pygame',
        '--hidden-import=mutagen',
        '--clean',
        '--noconfirm'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("ERROR: Build failed!")
        print(result.stderr)
        sys.exit(1)
    
    print("✓ Build successful!")

def prepare_installer_files():
    print("\n=== Preparing installer files ===\n")
    
    os.makedirs('installer_files', exist_ok=True)
    
    files_to_copy = [
        ('dist/wmus.exe', 'installer_files/wmus.exe'),
        ('config.json', 'installer_files/config.json'),
    ]
    
    if os.path.exists('README.md'):
        files_to_copy.append(('README.md', 'installer_files/README.md'))
    
    for src, dst in files_to_copy:
        shutil.copy(src, dst)
        print(f"✓ Copied {os.path.basename(src)}")
    
    print(f"\n=== Ready for Inno Setup ===")
    print(f"Files prepared in installer_files/")
    print(f"Now compile wmus-installer.iss with Inno Setup")

if __name__ == "__main__":
    print(f"Building wmus v{VERSION}\n")
    remove_old_builds()
    build_executable()
    prepare_installer_files()
    print("\n✓ Build process complete!")