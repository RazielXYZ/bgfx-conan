from conan import ConanFile
from conan.tools.files import rmdir, rm, copy, rename, replace_in_file
from conan.tools.build import check_min_cppstd
from conan.tools.scm import Git
from conan.tools.layout import basic_layout
from conan.tools.microsoft import is_msvc, check_min_vs, is_msvc_static_runtime
from conan.tools.apple import fix_apple_shared_install_name, is_apple_os
from conan.tools.scm import Version
from conan.errors import ConanInvalidConfiguration
from conan.tools.microsoft import MSBuild, VCVars
from conan.tools.gnu import Autotools, AutotoolsToolchain
from conan.tools.env import VirtualBuildEnv
from pathlib import Path
import os

required_conan_version = ">=1.50.0"

class bgfxConan(ConanFile):
    name = "bgfx"
    license = "BSD-2-Clause"
    homepage = "https://github.com/bkaradzic/bgfx"
    url = "https://github.com/RazielXYZ/bgfx-conan"
    description = "Cross-platform, graphics API agnostic, \"Bring Your Own Engine/Framework\" style rendering library."
    topics = ("lib-static", "C++", "C++17", "rendering", "gamedev")
    settings = "os", "compiler", "arch", "build_type"
    options = {"fPIC": [True, False], "shared": [True, False], "tools": [True, False], "rtti": [True, False], "profiler": [True, False], "bx_version": [None, "ANY"], "bimg_version": [None, "ANY"]}
    default_options = {"fPIC": True, "shared": False, "rtti": True, "tools": False, "profiler": False}

    invalidPackageExceptionText = "Less lib files found for copy than expected. Aborting."
    expectedNumLibs = 1

    @property
    def _bx_url(self):
        return "https://github.com/bkaradzic/bx.git"
    
    @property
    def _bimg_url(self):
        return "https://github.com/bkaradzic/bimg.git"
    
    @property
    def _bgfx_url(self):
        return "https://github.com/bkaradzic/bgfx.git"

    @property
    def _bx_folder(self):
        return "bx"

    @property
    def _bimg_folder(self):
        return "bimg"
    
    @property
    def _bgfx_folder(self):
        return "bgfx"

    @property
    def _bgfx_path(self):
        return os.path.join(self.source_folder, self._bgfx_folder)

    @property
    def _genie_extra(self):
        genie_extra = ""
        if is_msvc(self) and not is_msvc_static_runtime(self):
            genie_extra += " --with-dynamic-runtime"
        if self.options.shared:
            genie_extra += " --with-shared-lib"
        if self.options.profiler:
            genie_extra += " --with-profiler"
        if self.options.tools:
            genie_extra += " --with-tools"
        return genie_extra

    @property
    def _lib_target_prefix(self):
        if self.settings.os == "Windows":
            return "libs\\"
        else:
            return ""

    @property
    def _tool_target_prefix(self):
        if self.settings.os == "Windows":
            return "tools\\"
        else:
            return ""
        
    @property
    def _shaderc_target_prefix(self):
        if self.settings.os == "Windows":
            return "shaderc\\"
        else:
            return ""

    @property
    def _projs(self):
        if self.options.shared:
            projs = [f"{self._lib_target_prefix}bgfx-shared-lib"]
        else:
            projs = [f"{self._lib_target_prefix}bgfx"]
        if self.options.tools:
            projs.extend([f"{self._tool_target_prefix}{self._shaderc_target_prefix}shaderc",
                          f"{self._tool_target_prefix}texturev",
                          f"{self._tool_target_prefix}geometryc",
                          f"{self._tool_target_prefix}geometryv"])
        return projs

    @property
    def _compiler_required(self):
        return {
            "gcc": "8",
            "clang": "11",
            "apple-clang": "12",
            "msvc": "192",
            "Visual Studio": "16"
        }

    @property
    def _settings_build(self):
        return getattr(self, "settings_build", self.settings)

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def layout(self):
        basic_layout(self, src_folder="src")

    def requirements(self):
        # bgfx's C99 API absolutely requires a header from bx so we need those to be transitive
        if self.options.bx_version is None or str(self.options.bx_version) == "None":
            self.output.highlight("bx version is not specified; using latest available")
            self.requires("bx/[>=1.18.97]@bx/rolling", transitive_headers=True)
        else:
            self.requires(f"bx/{self.options.bx_version}@bx/rolling", transitive_headers=True)
        if self.options.bimg_version is None or str(self.options.bimg_version) == "None":
            self.output.highlight("bimg version is not specified; using latest available")
            self.requires("bimg/[>=1.3.67]@bimg/rolling")
        else:
            self.requires(f"bimg/{self.options.bimg_version}@bimg/rolling")
        self.requires("opengl/system")

    def package_id(self):
        if self.info.settings.compiler == "msvc":
            del self.info.settings.compiler.cppstd

    def configure(self):
        self.options["bimg/*"].bx_version = self.options.bx_version

    def set_version(self):
        if not self.version:
            self.output.info("Setting version from git.")
            rmdir(self, self._bgfx_folder)
            git = Git(self, folder=self._bgfx_folder)
            git.clone(self._bgfx_url, target=".", args=["--filter=tree:0"])
            # Hackjob semver! Versioning by commit seems rather annoying for users, so let's version by commit count
            numCommits = int(git.run("rev-list --count master"))
            verMajor = 1 + (numCommits // 10000)
            verMinor = (numCommits // 100) % 100
            verRev = numCommits % 100
            self.output.highlight(f"Version {verMajor}.{verMinor}.{verRev}")
            self.version = f"{verMajor}.{verMinor}.{verRev}"

    def validate(self):
        if not self.options.get_safe("fPIC", True):
            raise ConanInvalidConfiguration("This package does not support builds without fPIC.")
        if self.settings.compiler.get_safe("cppstd"):
            check_min_cppstd(self, 17)
        if Version(self.dependencies["bimg"].ref.version) < "1.3.30" and self.settings.os in ["Linux", "FreeBSD"] and self.settings.arch == "x86_64" and self.settings_build.arch == "x86":
            raise ConanInvalidConfiguration("The depended on version of the bimg cannot be cross-built to Linux x86 due to old astc breaking that.")
        check_min_vs(self, 191)
        if not is_msvc(self):
            try:
                minimum_required_compiler_version = self._compiler_required[str(self.settings.compiler)]
                if Version(self.settings.compiler.version) < minimum_required_compiler_version:
                    raise ConanInvalidConfiguration("This package requires C++17 support. The current compiler does not support it.")
            except KeyError:
                self.output.warn("This recipe has no checking for the current compiler. Please consider adding it.")
            if self.settings.os == "Windows" and self.settings.arch != "x86_64":
                raise ConanInvalidConfiguration("Building with mingw on Windows requires 64bit Windows and x86_64-w64-mingw32-g++.")

    def build_requirements(self):
        self.tool_requires("genie/1181")
        if not is_msvc(self) and self._settings_build.os == "Windows":
            if self.settings.os == "Windows": # building for windows mingw
                self.win_bash = True
                if not self.conf.get("tools.microsoft.bash:path", check_type=str):
                    self.tool_requires("msys2/cci.latest")
            else: # cross-compiling for something else, probably android; get native make
                self.tool_requires("make/[>=4.4.1]")
        if self.settings.os == "Android" and "ANDROID_NDK_ROOT" not in os.environ:
            self.tool_requires("android-ndk/[>=r26d]")

    def cloneVersion(self, folder, url, version):
        git = Git(self, folder=folder)
        git.clone(url, target=".", args=["--filter=tree:0"])
        self.output.info(f"Getting {folder} version {version}")
        numCommitsLatest = int(git.run("rev-list --count master"))
        splitVer = str(version).split(".")
        numCommitsBack = numCommitsLatest - (int(splitVer[2]) + int(splitVer[1]) * 100 + (int(splitVer[0]) - 1) * 10000)
        if numCommitsBack > 0:
            git.run(f"checkout HEAD~{numCommitsBack}")
        self.output.info(git.run("show -s"))

    def source(self):
        # bgfx requires bx and bimg source to build
        self.output.info("Getting source")
        self.cloneVersion(self._bx_folder, self._bx_url, self.dependencies["bx"].ref.version)
        self.cloneVersion(self._bimg_folder, self._bimg_url, self.dependencies["bimg"].ref.version)
        self.cloneVersion(self._bgfx_folder, self._bgfx_url, self.version)

    def generate(self):
        vbe = VirtualBuildEnv(self)
        vbe.generate()
        if is_msvc(self):
            tc = VCVars(self)
            tc.generate()
        else:
            tc = AutotoolsToolchain(self)
            tc.generate()

    def build(self):
        # Patch rtti
        if self.options.rtti:
            self.output.info("Disabling no-rtti.")
            replace_in_file(self, os.path.join(self.source_folder, self._bx_folder, "scripts", "toolchain.lua"),
                            "\"NoRTTI\",", "")
        # Patch astcenc
        # if self.settings.arch == "x86" or self.settings_build.arch == "x86":
        #     self.output.info("Disabling ASTCENC_POPCNT.")
        #     replace_in_file(self, os.path.join(self.source_folder, self.bimgFolder, "3rdparty", "astc-encoder", "source", "astcenc_mathlib.h"),
        #         "#define ASTCENC_POPCNT 1", "#define ASTCENC_POPCNT 0")
        #     replace_in_file(self, os.path.join(self.source_folder, self.bimgFolder, "3rdparty", "astc-encoder", "source", "astcenc_vecmathlib_sse_4.h"),
        #         "#if ASTCENC_POPCNT >= 1", "#if false")

        if is_msvc(self):
            # Conan to Genie translation maps
            vs_ver_to_genie = {"17": "2022", "16": "2019", "15": "2017",
                                "194": "2022", "193": "2022", "192": "2019", "191": "2017"}

            # Use genie directly, then msbuild on specific projects based on requirements
            genie_VS = f"vs{vs_ver_to_genie[str(self.settings.compiler.version)]}"
            genie_gen = f"{self._genie_extra} {genie_VS}"
            self.run(f"genie {genie_gen}", cwd=self._bgfx_path)

            msbuild = MSBuild(self)
            # customize to Release when RelWithDebInfo
            msbuild.build_type = "Debug" if self.settings.build_type == "Debug" else "Release"
            # use Win32 instead of the default value when building x86
            msbuild.platform = "Win32" if self.settings.arch == "x86" else msbuild.platform
            msbuild.build(os.path.join(self._bgfx_path, ".build", "projects", genie_VS, "bgfx.sln"), targets=self._projs)
        else:
            # Not sure if XCode can be spefically handled by conan for building through, so assume everything not VS is make
            # gcc-multilib and g++-multilib required for 32bit cross-compilation, should see if we can check and install through conan
            
            # Conan to Genie translation maps
            compiler_str = str(self.settings.compiler)
            compiler_and_os_to_genie = {"Windows": f"--gcc=mingw-{compiler_str}", "Linux": f"--gcc=linux-{compiler_str}",
                                        "FreeBSD": "--gcc=freebsd", "Macos": "--gcc=osx",
                                        "Android": "--gcc=android", "iOS": "--gcc=ios"}
            gmake_os_to_proj = {"Windows": "mingw", "Linux": "linux", "FreeBSD": "freebsd", "Macos": "osx", "Android": "android", "iOS": "ios"}
            gmake_android_arch_to_genie_suffix = {"x86": "-x86", "x86_64": "-x86_64", "armv8": "-arm64", "armv7": "-arm"}
            gmake_arch_to_genie_suffix = {"x86": "-x86", "x86_64": "-x64", "armv8": "-arm64", "armv7": "-arm"}
            os_to_use_arch_config_suffix = {"Windows": False, "Linux": False, "FreeBSD": False, "Macos": True, "Android": True, "iOS": True}

            build_type_to_make_config = {"Debug": "config=debug", "Release": "config=release"}
            arch_to_make_config_suffix = {"x86": "32", "x86_64": "64"}
            os_to_use_make_config_suffix = {"Windows": True, "Linux": True, "FreeBSD": True, "Macos": False, "Android": False, "iOS": False}

            # Generate projects through genie
            genie_args = f"{self._genie_extra} {compiler_and_os_to_genie[str(self.settings.os)]}"
            if os_to_use_arch_config_suffix[str(self.settings.os)]:
                if (self.settings.os == "Android"):
                    genie_args += F"{gmake_android_arch_to_genie_suffix[str(self.settings.arch)]}"
                else:
                    genie_args += f"{gmake_arch_to_genie_suffix[str(self.settings.arch)]}"
            genie_args += " gmake"
            self.run(f"genie {genie_args}", cwd=self._bgfx_path)

            # Build project folder and path from given settings
            proj_folder = f"gmake-{gmake_os_to_proj[str(self.settings.os)]}-{compiler_str}"
            if os_to_use_arch_config_suffix[str(self.settings.os)]:
                if (self.settings.os == "Android"):
                    proj_folder += gmake_android_arch_to_genie_suffix[str(self.settings.arch)]
                else:
                    proj_folder += gmake_arch_to_genie_suffix[str(self.settings.arch)]
            proj_path = os.path.sep.join([self._bgfx_path, ".build", "projects", proj_folder])

            # Build make args from settings
            conf = build_type_to_make_config[str(self.settings.build_type)]
            if os_to_use_make_config_suffix[str(self.settings.os)]:
                conf += arch_to_make_config_suffix[str(self.settings.arch)]
            if self.settings.os == "Windows":
                if "msys2" in self.dependencies.build:
                    self.run("if [ ! -d /mingw64 ]; then mkdir /mingw64; fi")
                    self.run("pacman -Sy mingw-w64-x86_64-gcc --needed --noconfirm")
                    mingw = "MINGW=$MSYS_ROOT/mingw64"
                else:
                    mingw = "MINGW=$MINGW" # user is expected to have an env var pointing to mingw; x86_64-w64-mingw32-g++ is expected in $MINGW/bin/
                proj_path = proj_path.replace("\\", "/") # Fix path for linux style...
            else:
                mingw = ""
            autotools = Autotools(self)
            # Build with make
            for proj in self._projs:
                autotools.make(target=proj, args=["-R", f"-C {proj_path}", mingw, conf])

    def package(self):
        # Set platform suffixes and prefixes 
        if self.settings.os == "Windows" and is_msvc(self):
            lib_ext = ["*.lib", "*.pdb"]
            package_lib_prefix = ""
        else:
            lib_ext = ["*.a"]
            if self.options.shared:
                lib_ext.extend(["*.so"]) # But Linux .so files go in /lib
            package_lib_prefix = "lib"

        # Get build bin folder
        for out_dir in os.listdir(os.path.join(self._bgfx_path, ".build")):
            if not out_dir=="projects":
                build_bin = os.path.join(self._bgfx_path, ".build", out_dir, "bin")
                break

        # Copy license
        copy(self, pattern="LICENSE", dst=os.path.join(self.package_folder, "licenses"), src=self._bgfx_path)
        # Copy includes
        copy(self, pattern="*.h", dst=os.path.join(self.package_folder, "include"), src=os.path.join(self._bgfx_path, "include"))
        copy(self, pattern="*.inl", dst=os.path.join(self.package_folder, "include"), src=os.path.join(self._bgfx_path, "include"))
        # Copy libs
        if len(copy(self, pattern=lib_ext[0], dst=os.path.join(self.package_folder, "lib"), src=build_bin, keep_path=False))  < self.expectedNumLibs:
            raise Exception(self.invalidPackageExceptionText)
        if self.options.shared:
            copy(self, pattern="*.dll", dst=os.path.join(self.package_folder, "bin"), src=build_bin, keep_path=False)
        # Debug info files are optional, so no checking
        if len(lib_ext) > 1:
            for ind in range(1, len(lib_ext)):
                copy(self, pattern=lib_ext[ind], dst=os.path.join(self.package_folder, "lib"), src=build_bin, keep_path=False)

        # Copy tools
        if self.options.tools:
            copy(self, pattern="shaderc*", dst=os.path.join(self.package_folder, "bin"), src=build_bin, keep_path=False)
            copy(self, pattern="texturev*", dst=os.path.join(self.package_folder, "bin"), src=build_bin, keep_path=False)
            copy(self, pattern="geometryc*", dst=os.path.join(self.package_folder, "bin"), src=build_bin, keep_path=False)
            copy(self, pattern="geometryv*", dst=os.path.join(self.package_folder, "bin"), src=build_bin, keep_path=False)
            for bgfxFile in Path(os.path.join(self.package_folder, "bin")).glob("*shaderc*"):
                rename(self, os.path.join(self.package_folder, "bin", bgfxFile.name), 
                        os.path.join(self.package_folder, "bin", f"shaderc{bgfxFile.suffix}"))
            for bgfxFile in Path(os.path.join(self.package_folder, "bin")).glob("*texturev*"):
                rename(self, os.path.join(self.package_folder, "bin", bgfxFile.name), 
                        os.path.join(self.package_folder, "bin", f"texturev{bgfxFile.suffix}"))
            for bgfxFile in Path(os.path.join(self.package_folder, "bin")).glob("*geometryc*"):
                rename(self, os.path.join(self.package_folder, "bin", bgfxFile.name), 
                        os.path.join(self.package_folder, "bin", f"geometryc{bgfxFile.suffix}"))
            for bgfxFile in Path(os.path.join(self.package_folder, "bin")).glob("*geometryv*"):
                rename(self, os.path.join(self.package_folder, "bin", bgfxFile.name), 
                        os.path.join(self.package_folder, "bin", f"geometryv{bgfxFile.suffix}"))
            rm(self, pattern="*shaderc*", folder=os.path.join(self.package_folder, "lib"))
            rm(self, pattern="*texturev*", folder=os.path.join(self.package_folder, "lib"))
            rm(self, pattern="*geometryc*", folder=os.path.join(self.package_folder, "lib"))
            rm(self, pattern="*geometryv*", folder=os.path.join(self.package_folder, "lib"))
            rm(self, pattern="*example*", folder=os.path.join(self.package_folder, "lib"))
            rm(self, pattern="*fcpp*", folder=os.path.join(self.package_folder, "lib"))
            rm(self, pattern="*glsl*", folder=os.path.join(self.package_folder, "lib"))
            rm(self, pattern="*spirv*", folder=os.path.join(self.package_folder, "lib"))

        # Rename for consistency across platforms and configs
        if not (is_apple_os(self) and self.options.shared): #Apparently apple dylibs break if renamed
            for out_file in Path(os.path.join(self.package_folder, "lib")).glob("*bgfx*"):
                if out_file.suffix != ".pdb":
                    rename(self, os.path.join(self.package_folder, "lib", out_file.name), 
                            os.path.join(self.package_folder, "lib", f"{package_lib_prefix}bgfx{out_file.suffix}"))
        
        # Delete unwanted output    
        rm(self, pattern="*bx*", folder=os.path.join(self.package_folder, "lib"))
        rm(self, pattern="*bimg*", folder=os.path.join(self.package_folder, "lib"))

    def package_info(self):
        self.cpp_info.includedirs = ["include"]
        if self.options.shared and self.settings.os in ["Macos", "iOS"]:
            self.cpp_info.libs = [f"bgfx-shared-lib{self.settings.build_type}"]
        else:
            self.cpp_info.libs = ["bgfx"]

        if self.options.shared:
            self.cpp_info.defines.extend(["BGFX_SHARED_LIB_USE=1"])

        if self.settings.os == "Windows":
            self.cpp_info.system_libs.extend(["gdi32"])
            if not is_msvc(self):
                self.cpp_info.system_libs.extend(["comdlg32"])
        elif self.settings.os in ["Linux", "FreeBSD"]:
            self.cpp_info.system_libs.extend(["X11", "GL"])
        elif self.settings.os in ["Macos", "iOS"]:
            self.cpp_info.frameworks.extend(["CoreFoundation", "AppKit", "IOKit", "QuartzCore", "Metal"])
            if self.settings.os in ["Macos"]:
                self.cpp_info.frameworks.extend(["OpenGL"])
            else:
                self.cpp_info.frameworks.extend(["OpenGLES", "UIKit"])
        elif self.settings.os in ["Android"]:
            self.cpp_info.system_libs.extend(["c", "dl", "m", "android", "log", "c++_shared", "EGL", "GLESv2"])

        self.cpp_info.set_property("cmake_file_name", "bgfx")
        self.cpp_info.set_property("cmake_target_name", "bgfx::bgfx")
        self.cpp_info.set_property("pkg_config_name", "bgfx")
