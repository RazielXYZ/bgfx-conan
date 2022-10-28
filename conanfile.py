from conan import ConanFile
from conan.tools.files import rmdir, copy, rename, rm
from conan.tools.build import check_min_cppstd
from conan.tools.scm import Git, Version
from conan.tools.layout import basic_layout
from conan.tools.microsoft import is_msvc
from conan.tools.microsoft import MSBuild, VCVars
from conan.tools.gnu import Autotools, AutotoolsToolchain
from conan.errors import ConanInvalidConfiguration
from pathlib import Path
import os

required_conan_version = ">=1.50.0"


class bgfxConan(ConanFile):
    name = "bgfx"
    license = "BSD-2-Clause"
    homepage = "https://github.com/bkaradzic/bgfx"
    url = "https://github.com/RazielXYZ/bgfx-conan"
    description = "Cross-platform, graphics API agnostic, \"Bring Your Own Engine/Framework\" style rendering library."
    topics = ("lib-static", "C++", "C++14", "rendering", "utility")
    settings = "os", "compiler", "arch", "build_type"
    options = {"shared": [True, False], "tools": [True, False]}
    default_options = {"shared": False, "tools": False}

    requires = "bx/[>=1.18.0]@bx/rolling", "bimg/[>=1.3.0]@bimg/rolling"

    invalidPackageExceptionText = "Less lib files found for copy than expected. Aborting."
    expectedNumLibs = 1
    bxFolder = "bx"
    bimgFolder = "bimg"
    bgfxFolder = "bgfx"
    
    vsVerToGenie = {"17": "2022", "16": "2019", "15": "2017",
                    "193": "2022", "192": "2019", "191": "2017"}

    gccOsToGenie = {"Windows": "--gcc=mingw-gcc", "Linux": "--gcc=linux-gcc", "Macos": "--gcc=osx", "Android": "--gcc=android", "iOS": "--gcc=ios"}
    gmakeOsToProj = {"Windows": "mingw", "Linux": "linux", "Macos": "osx", "Android": "android", "iOS": "ios"}
    gmakeArchToGenieSuffix = {"x86": "-x86", "x86_64": "-x64", "armv8": "-arm64", "armv7": "-arm"}
    osToUseArchConfigSuffix = {"Windows": False, "Linux": False, "Macos": True, "Android": True, "iOS": True}

    buildTypeToMakeConfig = {"Debug": "config=debug", "Release": "config=release"}
    archToMakeConfigSuffix = {"x86": "32", "x86_64": "64"}
    osToUseMakeConfigSuffix = {"Windows": True, "Linux": True, "Macos": False, "Android": False, "iOS": False}

    def package_id(self):
        if is_msvc(self):
            del self.info.settings.compiler.cppstd

    def configure(self):
        if self.settings.os == "Windows":
            self.libExt = ["*.lib", "*.pdb"]
            self.binExt = ["*.exe"]
            self.libTargetPrefix = "libs\\"
            self.toolTargetPrefix = "tools\\"
            self.shaderCPrefix = "shaderc\\"
            if self.options.shared:
                self.binExt.extend(["*.dll"]) # Windows dlls go in /bin
            self.packageLibPrefix = ""
            self.binFolder = "windows"
        elif self.settings.os in ["Linux", "FreeBSD"]:
            self.libExt = ["*.a"]
            self.binExt = []
            if self.options.shared:
                self.libExt.extend(["*.so"]) # But Linux .so files go in /lib
            self.libTargetPrefix = ""
            self.toolTargetPrefix = ""
            self.shaderCPrefix = ""
            self.packageLibPrefix = "lib"
            self.binFolder = "linux"
        elif self.settings.os == "Macos":
            self.libExt = ["*.a"]
            self.binExt = []
            if self.options.shared:
                self.libExt.extend(["*.so"])
            self.libTargetPrefix = ""
            self.toolTargetPrefix = ""
            self.shaderCPrefix = ""
            self.packageLibPrefix = "lib"
            self.binFolder = "darwin"

        self.genieExtra = ""
        if not self.options.shared:
            self.projs = [f"{self.libTargetPrefix}bgfx"]
        else:
            self.genieExtra += " --with-shared-lib"
            self.projs = [f"{self.libTargetPrefix}bgfx-shared-lib"]
        if self.options.tools:
            self.genieExtra += " --with-tools"
            self.projs.extend([f"{self.toolTargetPrefix}{self.shaderCPrefix}shaderc", f"{self.toolTargetPrefix}texturev", f"{self.toolTargetPrefix}geometryc", f"{self.toolTargetPrefix}geometryv"])

    def set_version(self):
        self.output.info("Setting version from git.")
        rmdir(self, self.bgfxFolder)
        git = Git(self, folder=self.bgfxFolder)
        git.clone(f"{self.homepage}.git", target=".")

        # Hackjob semver! Versioning by commit seems rather annoying for users, so let's version by commit count
        numCommits = int(git.run("rev-list --count master"))
        verMajor = 1 + (numCommits // 10000)
        verMinor = (numCommits // 100) % 100
        verRev = numCommits % 100
        self.output.highlight(f"Version {verMajor}.{verMinor}.{verRev}")
        self.version = f"{verMajor}.{verMinor}.{verRev}"

    def validate(self):
        if self.settings.compiler.get_safe("cppstd"):
            check_min_cppstd(self, 14)
        if Version(self.dependencies["bimg"].ref.version) < "1.3.30" and self.settings.os in ["Linux", "FreeBSD"] and self.settings.arch == "x86_64" and self.settings_build.arch == "x86":
            raise ConanInvalidConfiguration("The depended on version of the bimg cannot be cross-built to Linux x86 due to old astc breaking that.")

    def source(self):
        # bgfx requires bx and bimg source to build
        self.output.info("Getting source")
        gitBx = Git(self, folder=self.bxFolder)
        gitBx.clone("https://github.com/bkaradzic/bx.git", target=".")
        gitBimg = Git(self, folder=self.bimgFolder)
        gitBimg.clone("https://github.com/bkaradzic/bimg.git", target=".")
        gitBgfx = Git(self, folder=self.bgfxFolder)
        gitBgfx.clone(f"{self.homepage}.git", target=".")

    def generate(self):
        if is_msvc(self):
            tc = VCVars(self)
            tc.generate()
        else:
            tc = AutotoolsToolchain(self)
            tc.generate()

    def build(self):
        # Map conan compilers to genie input
        self.bxPath = os.path.join(self.source_folder, self.bxFolder)
        self.bimgPath = os.path.join(self.source_folder, self.bimgFolder)
        self.bgfxPath = os.path.join(self.source_folder, self.bgfxFolder)
        genie = os.path.join(self.bxPath, "tools", "bin", self.binFolder, "genie")
        if is_msvc(self):
            # Use genie directly, then msbuild on specific projects based on requirements
            genieVS = f"vs{self.vsVerToGenie[str(self.settings.compiler.version)]}"
            genieGen = f"{self.genieExtra} {genieVS}"
            self.run(f"{genie} {genieGen}", cwd=self.bgfxPath)

            # Build with MSBuild
            msbuild = MSBuild(self)
            # customize to Release when RelWithDebInfo
            msbuild.build_type = "Debug" if self.settings.build_type == "Debug" else "Release"
            # use Win32 instead of the default value when building x86
            msbuild.platform = "Win32" if self.settings.arch == "x86" else msbuild.platform
            msbuild.build(os.path.join(self.bgfxPath, ".build", "projects", genieVS, "bgfx.sln"), targets=self.projs)            
        else:
            # Not sure if XCode can be spefically handled by conan for building through, so assume everything not VS is make
            # Use genie with gmake gen, then make on specific projects based on requirements
            # gcc-multilib and g++-multilib required for 32bit cross-compilation, should see if we can check and install through conan
            
            # Generate projects through genie
            genieGen = f"{self.genieExtra} {self.gccOsToGenie[str(self.settings.os)]} gmake"
            self.run(f"{genie} {genieGen}", cwd=self.bgfxPath)

            # Build project folder and path from given settings
            projFolder = f"gmake-{self.gmakeOsToProj[str(self.settings.os)]}"
            if self.osToUseArchConfigSuffix[str(self.settings.os)]:
                projFolder += self.gmakeArchToGenieSuffix[str(self.settings.arch)]
            projPath = os.path.sep.join([self.bgfxPath, ".build", "projects", projFolder])

            # Build make args from settings
            conf = self.buildTypeToMakeConfig[str(self.settings.build_type)]
            if self.osToUseMakeConfigSuffix[str(self.settings.os)]:
                conf += self.archToMakeConfigSuffix[str(self.settings.arch)]
            autotools = Autotools(self)
            # Build with make
            for proj in self.projs:
                autotools.make(target=proj, args=["-R", f"-C {projPath}", conf])

    def package(self):
        # Get build bin folder
        for dir in os.listdir(os.path.join(self.bgfxPath, ".build")):
            if not dir=="projects":
                buildBin = os.path.join(self.bgfxPath, ".build", dir, "bin")
                break

        # Copy license
        copy(self, pattern="LICENSE", dst=os.path.join(self.package_folder, "licenses"), src=self.bgfxPath)
        # Copy includes
        copy(self, pattern="*.h", dst=os.path.join(self.package_folder, "include"), src=os.path.join(self.bgfxPath, "include"))
        copy(self, pattern="*.inl", dst=os.path.join(self.package_folder, "include"), src=os.path.join(self.bgfxPath, "include"))
        # Copy libs
        if len(copy(self, pattern=self.libExt[0], dst=os.path.join(self.package_folder, "lib"), src=buildBin, keep_path=False))  < self.expectedNumLibs:
            raise Exception(self.invalidPackageExceptionText)
        # Debug info files are optional, so no checking
        if len(self.libExt) > 1:
            for ind in range(1, len(self.libExt)):
                copy(self, pattern=self.libExt[ind], dst=os.path.join(self.package_folder, "lib"), src=buildBin, keep_path=False)

        # Copy tools
        if self.options.tools:
            copy(self, pattern=f"shaderc*", dst=os.path.join(self.package_folder, "bin"), src=buildBin, keep_path=False)
        if self.options.tools:
            copy(self, pattern=f"texturev*", dst=os.path.join(self.package_folder, "bin"), src=buildBin, keep_path=False)
        if self.options.tools:
            copy(self, pattern=f"geometryc*", dst=os.path.join(self.package_folder, "bin"), src=buildBin, keep_path=False)
        if self.options.tools:
            copy(self, pattern=f"geometryv*", dst=os.path.join(self.package_folder, "bin"), src=buildBin, keep_path=False)

        # Rename for consistency across platforms and configs
        for bxFile in Path(os.path.join(self.package_folder, "lib")).glob("*bgfx*"):
            rename(self, os.path.join(self.package_folder, "lib", bxFile.name), 
                    os.path.join(self.package_folder, "lib", f"{self.packageLibPrefix}bgfx{bxFile.suffix}"))
        for bxFile in Path(os.path.join(self.package_folder, "bin")).glob("*shaderc*"):
            rename(self, os.path.join(self.package_folder, "bin", bxFile.name), 
                    os.path.join(self.package_folder, "bin", f"shaderc{bxFile.suffix}"))
        for bxFile in Path(os.path.join(self.package_folder, "bin")).glob("*texturev*"):
            rename(self, os.path.join(self.package_folder, "bin", bxFile.name), 
                    os.path.join(self.package_folder, "bin", f"texturev{bxFile.suffix}"))
        for bxFile in Path(os.path.join(self.package_folder, "bin")).glob("*geometryc*"):
            rename(self, os.path.join(self.package_folder, "bin", bxFile.name), 
                    os.path.join(self.package_folder, "bin", f"geometryc{bxFile.suffix}"))
        for bxFile in Path(os.path.join(self.package_folder, "bin")).glob("*geometryv*"):
            rename(self, os.path.join(self.package_folder, "bin", bxFile.name), 
                    os.path.join(self.package_folder, "bin", f"geometryv{bxFile.suffix}"))
        
        rm(self, pattern="*bx*", folder=os.path.join(self.package_folder, "lib"))
        rm(self, pattern="*bimg*", folder=os.path.join(self.package_folder, "lib"))
        rm(self, pattern="*shaderc*", folder=os.path.join(self.package_folder, "lib"))
        rm(self, pattern="*texturev*", folder=os.path.join(self.package_folder, "lib"))
        rm(self, pattern="*geometryc*", folder=os.path.join(self.package_folder, "lib"))
        rm(self, pattern="*geometryv*", folder=os.path.join(self.package_folder, "lib"))
        rm(self, pattern="*example*", folder=os.path.join(self.package_folder, "lib"))
        rm(self, pattern="*fcpp*", folder=os.path.join(self.package_folder, "lib"))
        rm(self, pattern="*glsl*", folder=os.path.join(self.package_folder, "lib"))
        rm(self, pattern="*spirv*", folder=os.path.join(self.package_folder, "lib"))

    def package_info(self):
        self.cpp_info.includedirs = ["include"]
        self.cpp_info.libs = ["bgfx"]

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.cpp_info.system_libs.extend(["X11", "GL"])

        self.cpp_info.set_property("cmake_file_name", "bgfx")
        self.cpp_info.set_property("cmake_target_name", "bgfx::bgfx")
        self.cpp_info.set_property("pkg_config_name", "bgfx")

        #  TODO: to remove in conan v2 once cmake_find_package_* generators removed
        self.cpp_info.filenames["cmake_find_package"] = "bgfx"
        self.cpp_info.filenames["cmake_find_package_multi"] = "bgfx"
        self.cpp_info.names["cmake_find_package"] = "bgfx"
        self.cpp_info.names["cmake_find_package_multi"] = "bgfx"
