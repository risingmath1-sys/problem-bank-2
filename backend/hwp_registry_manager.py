"""
HWP Registry Manager (Enhanced)
Purpose: Automatically register FilePathCheckerModule in Windows Registry to suppress "Access Allowed" popups.
"""
import winreg
import os
import sys

class HwpRegistryManager:
    REG_PATH = r"Software\HNC\HwpAutomation\Modules"
    REG_PATH_64 = r"Software\HNC\HwpAutomation\Modules64"
    REG_PATH_CTRL = r"Software\HNC\HwpCtrl\Modules"
    MODULE_NAME = "FilePathCheckerModule"
    # Flexible DLL name search
    DLL_NAMES = ["FilePathCheckerModule.dll", "FilePathCheckerModuleExample.dll"]
    
    # Cache to avoid repeated file system searches
    _DLL_PATH_CACHE = None
    
    @staticmethod
    def _search_files(start_dir, target_names):
        print(f"Searching in {start_dir}...")
        for root, dirs, files in os.walk(start_dir):
            for target in target_names:
                if target in files:
                    return os.path.join(root, target)
        return None

    @classmethod
    def _find_hwp_dll(cls):
        """Find FilePathCheckerModule using Registry and Recursive Search"""
        
        # 1. Try to find Install Path from Registry
        search_keys = [
            r"SOFTWARE\HNC\Hwp\9.0",  # HWP 2014
            r"SOFTWARE\HNC\Hwp\10.0", # HWP 2018/NEO
            r"SOFTWARE\HNC\Hwp\11.0", # HWP 2020
            r"SOFTWARE\HNC\Hwp\12.0", # HWP 2022
            r"SOFTWARE\WOW6432Node\HNC\Hwp\9.0",
            r"SOFTWARE\WOW6432Node\HNC\Hwp\10.0",
            r"SOFTWARE\WOW6432Node\HNC\Hwp\11.0",
            r"SOFTWARE\WOW6432Node\HNC\Hwp\12.0",
        ]
        
        for key_path in search_keys:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                path, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                if path:
                    print(f"[Info] Found InstallPath in Registry: {path}")
                    # Check if DLL exists there or in subdirs
                    found = cls._search_files(path, cls.DLL_NAMES)
                    if found: return found
            except WindowsError:
                continue

        # 2. pyhwpx 패키지에서 탐색 (pip install pyhwpx)
        try:
            import site
            for site_dir in site.getsitepackages():
                pyhwpx_dll = os.path.join(site_dir, "pyhwpx", "FilePathCheckerModule.dll")
                if os.path.exists(pyhwpx_dll):
                    print(f"[Info] Found DLL in pyhwpx package: {pyhwpx_dll}")
                    return pyhwpx_dll
        except Exception:
            pass

        # 3. Brute-force search in Hnc directories
        roots = [
            r"C:\Program Files (x86)\Hnc",
            r"C:\Program Files\Hnc",
            r"C:\Program Files (x86)\Haansoft", # Old Haansoft users
            r"C:\Program Files\Haansoft"
        ]

        print("[Info] Searching standard directories for Security Module...")
        for root in roots:
            if os.path.exists(root):
                found = cls._search_files(root, cls.DLL_NAMES)
                if found: return found

        return None

    @classmethod
    def get_registered_value_name(cls):
        """
        Return the Value Name used in Registry (e.g., 'FilePathCheckerModule')
        
        ⚠️ CRITICAL: This returns the REGISTRY KEY NAME, NOT the DLL filename!
        
        Correct usage in hwp.RegisterModule():
            ✅ hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")  # Registry key name
            ❌ hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule.dll")  # Wrong!
        
        The registry key name must match the value name in:
        HKCU\\Software\\HNC\\HwpAutomation\\Modules
        """
        return cls.MODULE_NAME

    @classmethod
    def get_dll_path(cls):
        """Return the found or registered DLL path."""
        # Check cache first
        if cls._DLL_PATH_CACHE and os.path.exists(cls._DLL_PATH_CACHE):
            return cls._DLL_PATH_CACHE
        
        # First check if already registered
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH, 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, cls.MODULE_NAME)
            winreg.CloseKey(key)
            if os.path.exists(val):
                cls._DLL_PATH_CACHE = val
                return val
        except WindowsError:
            pass
            
        # If not, search for it
        found_path = cls._find_hwp_dll()
        if found_path:
            cls._DLL_PATH_CACHE = found_path
        return found_path

    @classmethod
    def ensure_registry_structure(cls):
        """Ensure all required registry keys exist (create if missing)"""
        paths_to_ensure = [cls.REG_PATH, cls.REG_PATH_64, cls.REG_PATH_CTRL]
        
        for reg_path in paths_to_ensure:
            try:
                # Try to create the key (will succeed even if it already exists)
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path)
                winreg.CloseKey(key)
                print(f"[Info] Ensured registry key exists: HKCU\\{reg_path}")
            except Exception as e:
                print(f"[Warning] Failed to create registry key {reg_path}: {e}")
        
        return True
    
    @classmethod
    def register_module(cls):
        """Register the module in HKCU"""
        # First ensure the registry structure exists
        cls.ensure_registry_structure()
        
        dll_path = cls._find_hwp_dll()
            
        if not dll_path:
            print("[Error] FilePathCheckerModule.dll (or Example) not found in any standard location.")
            return False
            
        print(f"[Info] Found DLL at: {dll_path}")
        
        try:
            # Clean path just in case (report emphasis: NO QUOTES)
            dll_path_clean = dll_path.replace('"', '').strip()
            
            paths_to_register = [cls.REG_PATH, cls.REG_PATH_64, cls.REG_PATH_CTRL]
            success_count = 0
            
            for reg_path in paths_to_register:
                try:
                    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path)
                    winreg.SetValueEx(key, cls.MODULE_NAME, 0, winreg.REG_SZ, dll_path_clean)
                    winreg.CloseKey(key)
                    print(f"[Success] Registered to HKCU\\{reg_path}")
                    success_count += 1
                except Exception as e:
                    print(f"[Warning] Failed to register to {reg_path}: {e}")
            
            return success_count > 0
        except Exception as e:
            print(f"[Error] Registry operation failed: {e}")
            return False

    @classmethod
    def check_registration(cls):
        """Check if already registered correctly"""
        try:
            # Check standard path
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH, 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, cls.MODULE_NAME)
            winreg.CloseKey(key)
            
            if not os.path.exists(val):
                print(f"[Warning] Registered DLL path does not exist: {val}")
                return False
                
            print(f"[Info] Current Registry Value: {val}")
            return True
            
        except WindowsError:
            print("[Info] Not currently registered (Standard Path).")
            return False

    @classmethod
    def repair_com_registry(cls):
        """
        [DEPRECATED] Attempt to repair HWP COM registration by running 'hwp.exe /regserver'.
        
        ⚠️ WARNING: This method should ONLY be run during installation or manual maintenance.
        DO NOT call this during runtime as it can cause:
        - COM registration conflicts
        - Infinite loops when called repeatedly
        - Process hangs due to synchronous execution
        
        Based on expert advice: /regserver is a one-time installation command,
        not a runtime recovery mechanism.
        
        For runtime issues, use process isolation instead (see hwp_core.py).
        """
        print("[WARNING] repair_com_registry() is DEPRECATED for runtime use!")
        print("[WARNING] This should only be run manually for maintenance.")
        print("[WARNING] Proceeding anyway...")
        try:
            # Find Hwp.exe path via Registry
            hwp_exe = None
            search_keys = [
                r"SOFTWARE\HNC\Hwp\9.0", r"SOFTWARE\HNC\Hwp\10.0", 
                r"SOFTWARE\HNC\Hwp\11.0", r"SOFTWARE\HNC\Hwp\12.0",
                r"SOFTWARE\WOW6432Node\HNC\Hwp\9.0", r"SOFTWARE\WOW6432Node\HNC\Hwp\10.0",
                r"SOFTWARE\WOW6432Node\HNC\Hwp\11.0", r"SOFTWARE\WOW6432Node\HNC\Hwp\12.0"
            ]
            
            for key_path in search_keys:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                    path, _ = winreg.QueryValueEx(key, "InstallPath")
                    winreg.CloseKey(key)
                    if path:
                        exe_candidate = os.path.join(path, "Hwp.exe")
                        if os.path.exists(exe_candidate):
                            hwp_exe = exe_candidate
                            break
                except:
                    continue
            
            if not hwp_exe:
                # Fallback search
                roots = [
                    r"C:\Program Files (x86)\Hnc\HOffice9\Bin",
                    r"C:\Program Files (x86)\Hnc",
                    r"C:\Program Files\Hnc"
                ]
                for root in roots:
                     candidate = os.path.join(root, "Hwp.exe")
                     # Also check subdirs
                     if os.path.exists(candidate):
                         hwp_exe = candidate
                         break
                     # Simple walk might be too slow, check specific bins
                     # HOffice9/Bin/Hwp.exe, HOffice2018/Bin...
                     
            if hwp_exe:
                print(f"[Info] Found Hwp.exe at: {hwp_exe}")
                print("[Info] Running safely: Hwp.exe /regserver ...")
                import subprocess
                subprocess.run([hwp_exe, "/regserver"], check=True)
                print("[Success] HWP COM Registry repaired.")
                return True
            else:
                print("[Error] Could not find Hwp.exe to run /regserver.")
                return False
                
        except Exception as e:
            print(f"[Error] Failed to repair COM registry: {e}")
            return False

if __name__ == "__main__":
    # Safe check of registration when run directly
    is_registered = HwpRegistryManager.check_registration()
    
    if is_registered:
        print("Module is currently registered.")
    else:
        print("Attempting to register module...")
        HwpRegistryManager.register_module()
        
    print("\n[Maintenance] To repair COM registry, call HwpRegistryManager.repair_com_registry() manually.")
