# Introduction 
This repo contains a self-versioning conan script for grabbing and building bgfx's rolling master. In the future, I will attempt to push a conan center bgfx package based on (a non self-versioning variant of) this.

# Getting Started
The script requires Python 3 to run, and conan installed. It is designed to work for both local and shared conan distributions, but is not suitable for conan center. It creates a semver-like version for bgfx based on commit count. Recommended reference is @bgfx/rolling.