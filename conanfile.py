from enum import auto
from importlib.metadata import requires
from conans import ConanFile, tools, MSBuild, AutoToolsBuildEnvironment
from pathlib import Path
import os

required_conan_version = ">=1.50.0"


class bxConan(ConanFile):
    name = "bgfx"
    license = "BSD-2-Clause"
    homepage = "https://github.com/bkaradzic/bgfx"
    url = "https://github.com/RazielXYZ/bgfx-conan"
    description = "Cross-platform, graphics API agnostic, \"Bring Your Own Engine/Framework\" style rendering library."
    topics = ("lib-static", "C++", "C++14", "rendering", "utility")
    settings = "os", "compiler", "arch", "build_type"
    options = {"shared": [True, False]}
    default_options = {"shared": False}

    requires = "bx/[>=1.18.0]", "bimg/[>=1.3.0]"

    invalidPackageExceptionText = "Less lib files found for copy than expected. Aborting."
    expectedNumLibs = 1
    bxFolder = "bx"
    bimgFolder = "bimg"
    bgfxFolder = "bgfx"
    

    vsVerToGenie = {"17": "2022", "16": "2019", "15": "2017"}

    gccOsToGenie = {"Windows": "--gcc=mingw-gcc", "Linux": "--gcc=linux-gcc", "Macos": "--gcc=osx", "Android": "--gcc=android", "iOS": "--gcc=ios"}
    gmakeOsToProj = {"Windows": "mingw", "Linux": "linux", "Macos": "osx", "Android": "android", "iOS": "ios"}
    gmakeArchToGenieSuffix = {"x86": "-x86", "x86_64": "-x64", "armv8": "-arm64", "armv7": "-arm"}
    osToUseArchConfigSuffix = {"Windows": False, "Linux": False, "Macos": True, "Android": True, "iOS": True}

    buildTypeToMakeConfig = {"Debug": "config=debug", "Release": "config=release"}
    archToMakeConfigSuffix = {"x86": "32", "x86_64": "64"}
    osToUseMakeConfigSuffix = {"Windows": True, "Linux": True, "Macos": False, "Android": False, "iOS": False}

    def configure(self):
        if self.settings.os == "Windows":
            self.libExt = ["*.lib"]
            self.binExt = ["*.exe"]
            if self.options.shared:
                self.binExt.extend(["*.dll"]) # Windows dlls go in /bin
            self.libExt.extend(["*.pdb"])
            self.packageLibExt = ""
            self.binFolder = "windows"
        elif self.settings.os == "Linux":
            self.libExt = ["*.a"]
            if self.options.shared:
                self.libExt.extend(["*.so"]) # But Linux .so files go in /lib
            self.packageLibExt = ".a"
            self.binFolder = "linux"
        self.toolsFolder = cwd=os.path.sep.join([".", "tools", "bin", self.binFolder])

    def set_version(self):
        self.output.info("Setting version from git.")
        tools.rmdir(self.bgfxFolder)
        git = tools.Git(folder=self.bgfxFolder)
        git.clone(f"{self.homepage}.git", "master")

        # Hackjob semver! Versioning by commit seems rather annoying for users, so let's version by commit count
        numCommits = int(git.run("rev-list --count master"))
        verMajor = 1 + (numCommits // 10000)
        verMinor = (numCommits // 100) % 100
        verRev = numCommits % 100
        self.output.highlight(f"Version {verMajor}.{verMinor}.{verRev}")
        self.version = f"{verMajor}.{verMinor}.{verRev}"

    def source(self):
        # bgfx requires bx and bimg source to build
        self.output.info("Getting source")
        gitBx = tools.Git(folder=self.bxFolder)
        gitBx.clone("https://github.com/bkaradzic/bx.git", "master")
        gitBimg = tools.Git(folder=self.bimgFolder)
        gitBimg.clone("https://github.com/bkaradzic/bimg.git", "master")
        gitBgfx = tools.Git(folder=self.bgfxFolder)
        gitBgfx.clone(f"{self.homepage}.git", "master")

    def build(self):
        # Map conan compilers to genie input
        genie = os.path.sep.join(["..", self.bxFolder, self.toolsFolder, "genie"])
        if self.settings.compiler == "Visual Studio":
            # Use genie directly, then msbuild on specific projects based on requirements
            genieGen = f"vs{self.vsVerToGenie[str(self.settings.compiler.version)]}"
            self.output.highlight(genieGen)
            self.run(f"{genie} {genieGen}", cwd=self.bgfxFolder)
            msbuild = MSBuild(self)
            msbuild.build(f"{self.bgfxFolder}\\.build\\projects\\{genieGen}\\bgfx.vcxproj")
        else:
            # Not sure if XCode can be spefically handled by conan for building through, so assume everything not VS is make
            # Use genie with gmake gen, then make on specific projects based on requirements
            # gcc-multilib and g++-multilib required for 32bit cross-compilation, should see if we can check and install through conan
            
            # Generate projects through genie
            genieGen = f"{self.gccOsToGenie[str(self.settings.os)]} gmake"
            self.run(f"{genie} {genieGen}", cwd=self.bgfxFolder)

            # Build project folder and path from given settings
            projFolder = f"gmake-{self.gmakeOsToProj[str(self.settings.os)]}"
            if self.osToUseArchConfigSuffix[str(self.settings.os)]:
                projFolder += self.gmakeArchToGenieSuffix[str(self.settings.arch)]
            projPath = os.path.sep.join([".", self.bxFolder, ".build", "projects", projFolder])

            autotools = AutoToolsBuildEnvironment(self)
            with tools.environment_append(autotools.vars):
                # Build make args from settings
                conf = self.buildTypeToMakeConfig[str(self.settings.build_type)]
                if self.osToUseMakeConfigSuffix[str(self.settings.os)]:
                    conf += self.archToMakeConfigSuffix[str(self.settings.arch)]

                # Compile with make
                self.run(f"make {conf}", cwd=projPath)

    def package(self):
        # Copy includes
        self.copy("*.h", dst="include", src=f"{self.bgfxFolder}/include/")
        self.copy("*.inl", dst="include", src=f"{self.bgfxFolder}/include/")
        # Copy libs and debug info
        if len(self.copy(self.libExt[0], dst="lib", src=f"{self.bgfxFolder}/.build/", keep_path=False))  < self.expectedNumLibs:
            raise Exception(self.invalidPackageExceptionText)
        # Debug info files are optional, so no checking
        if len(self.libExt) > 1:
            for ind in range(1, len(self.libExt)):
                self.copy(self.libExt[ind], dst="lib", src=f"{self.bgfxFolder}/.build/", keep_path=False)
        for bgfxFile in Path(f"{self.package_folder}/lib").glob("*bgfx*"):
            tools.rename(f"{self.package_folder}/lib/{bgfxFile.name}", f"{self.package_folder}/lib/bgfx{bgfxFile.suffix}")
        tools.remove_files_by_mask(f"{self.package_folder}/lib", "*bx*")
            

    def package_info(self):
        self.cpp_info.includedirs = ["include"]
        self.cpp_info.libs = [f"bgfx{self.packageLibExt}"]

