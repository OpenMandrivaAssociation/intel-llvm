# Intel oneAPI DPC++ compiler, installed beside the system clang.
# Offline build: every FetchContent pin is a Source. The build has no network.

%global _disable_lto 1
# -flto exhausts the linker. -g3 does not fit the builder disk (IGC's
# bundled LLVM 22 already hit ENOSPC with it). -w matches the IGC build:
# the distro -Werror=format-security fires on LLVM sources.
%global optflags %(echo %{optflags} | sed -e 's/ -flto//g; s/ -g3//g; s/ -gdwarf-4//g') -w -g0
%global debug_package %{nil}
%global _find_debuginfo_dwz_opts %{nil}

%global spirv_headers_commit 9268f3057354a2cb65991ba5f38b16d81e803692
%global vc_commit 60cea7590bd022d95f5cf336ee765033bd114d69
%global emhash_commit 5e131ba09a5290823fe71099d9c35eb5df5345b6
%global umf_ver 1.1.0
%global phmap_commit 8a889d3699b3c09ade435641fb034427f3fd12b6
%global neo_ver 26.35.39758.11

Name:		intel-llvm
Version:	7.1.1
Release:	1
Summary:	Intel oneAPI DPC++ compiler (icpx)
Group:		Development/C++
License:	Apache-2.0 WITH LLVM-exception
URL:		https://github.com/intel/llvm
Source0:	%{url}/archive/refs/tags/v%{version}/intel-llvm-v%{version}.tar.gz
Source1:	https://github.com/KhronosGroup/SPIRV-Headers/archive/%{spirv_headers_commit}/SPIRV-Headers-%{spirv_headers_commit}.tar.gz
Source2:	https://github.com/intel/vc-intrinsics/archive/%{vc_commit}/vc-intrinsics-%{vc_commit}.tar.gz
Source3:	https://github.com/ktprime/emhash/archive/%{emhash_commit}/emhash-%{emhash_commit}.tar.gz
Source4:	https://github.com/oneapi-src/unified-memory-framework/archive/refs/tags/v%{umf_ver}/unified-memory-framework-v%{umf_ver}.tar.gz
Source5:	https://github.com/greg7mdp/parallel-hashmap/archive/%{phmap_commit}/parallel-hashmap-%{phmap_commit}.tar.gz
# Experimental Level Zero headers (ze_intel_gpu.h). The loader package does
# not ship these; compute-runtime does, but this package must not wait on it.
Source6:	https://github.com/intel/compute-runtime/archive/refs/tags/%{neo_ver}/compute-runtime-%{neo_ver}.tar.gz
# Ninja 1.13 errors if link_job_pool is declared twice.
Patch0:		0001-ninja-link-pool-once.patch
# libstdc++fs is not shipped; std::filesystem lives in libstdc++.
Patch1:		0002-optional-libstdcxxfs.patch

# Host compiler. It emits SPIR-V for the GPU and builds for the
# architecture it is compiled on, including aarch64.

BuildRequires:	cmake
BuildRequires:	ninja
BuildRequires:	python
BuildRequires:	git-core
BuildRequires:	pkgconfig(zlib)
BuildRequires:	pkgconfig(libzstd)
BuildRequires:	pkgconfig(libxml-2.0)
BuildRequires:	pkgconfig(ncurses)
BuildRequires:	pkgconfig(libffi)
BuildRequires:	pkgconfig(level-zero) >= 1.32.0
BuildRequires:	pkgconfig(hwloc)
BuildRequires:	pkgconfig(OpenCL)
BuildRequires:	pkgconfig(OpenCL-Headers)
# gcc -dumpmachine is the directory under /usr/lib64/gcc.
BuildRequires:	gcc

Provides:	bundled(spirv-headers)
Provides:	bundled(vc-intrinsics)
Provides:	bundled(emhash)
Provides:	bundled(unified-memory-framework)
Provides:	bundled(parallel-hashmap)

%description
Intel's LLVM-based DPC++ / C++ compiler with SYCL support (icx and icpx).

Installed under %{_libdir}/intel-llvm so it does not replace the system
clang, the system libsycl (libLLVMSYCL) or /usr/bin/sycl-ls. icx and icpx
are symlinked into %{_bindir}. libsycl.so is registered via ld.so.conf.d.

%prep
%autosetup -n llvm-%{version} -p1

mkdir -p %{_builddir}/spirv-headers-llvm %{_builddir}/vc-intrinsics \
	%{_builddir}/emhash/emhash %{_builddir}/umf \
	%{_builddir}/parallel-hashmap %{_builddir}/neo-l0-headers
tar -xf %{SOURCE1} -C %{_builddir}/spirv-headers-llvm --strip-components=1
tar -xf %{SOURCE2} -C %{_builddir}/vc-intrinsics --strip-components=1
tar -xf %{SOURCE3} -C %{_builddir}/emhash --strip-components=1
tar -xf %{SOURCE4} -C %{_builddir}/umf --strip-components=1
tar -xf %{SOURCE5} -C %{_builddir}/parallel-hashmap --strip-components=1
# bsdtar has no --wildcards. Keep level_zero/ as a subdirectory so
# #include <level_zero/ze_intel_gpu.h> resolves.
mkdir -p %{_builddir}/neo-l0-src
tar -xf %{SOURCE6} -C %{_builddir}/neo-l0-src
cp -a %{_builddir}/neo-l0-src/compute-runtime-%{neo_ver}/level_zero/include/level_zero \
	%{_builddir}/neo-l0-headers/
rm -rf %{_builddir}/neo-l0-src
# FetchEmhash declares SOURCE_SUBDIR emhash, but this commit keeps
# CMakeLists.txt and the headers at the repository root. A dummy project
# satisfies the subdirectory; the headers stay on the root include path.
cat > %{_builddir}/emhash/emhash/CMakeLists.txt <<'EOF'
cmake_minimum_required(VERSION 3.20)
project(emhash_fetch LANGUAGES NONE)
EOF

%build
# icpx is produced by this build. Host compile uses the system compiler.
export CFLAGS="%{optflags}"
export CXXFLAGS="%{optflags}"
export LDFLAGS="$(printf '%s' '%{build_ldflags}' | sed -e 's/-Wl,--no-undefined//g')"
# The compiler is installed under %{_libdir}/intel-llvm, so it will not
# find the system GCC by walking up from its own prefix. The triple has
# to be the distro one (znver1- or aarch64-openmandriva-linux-gnu), not
# the generic *-unknown-linux-gnu triple, or libdevice cannot see <cstddef>.
_triple=$(gcc -dumpmachine)
python buildbot/configure.py \
	--no-assertions \
	--l0-headers %{_includedir}/level_zero \
	--l0-loader %{_libdir}/libze_loader.so \
	--obj-dir %{_builddir}/intel-llvm-build \
	--cmake-opt=-DSYCL_INCLUDE_TESTS=OFF \
	--cmake-opt=-DLLVM_INCLUDE_BENCHMARKS=OFF \
	--cmake-opt=-DLLVM_INCLUDE_EXAMPLES=OFF \
	--cmake-opt=-DLLVM_BUILD_EXAMPLES=OFF \
	--cmake-opt=-DLLVM_USE_STATIC_ZSTD=OFF \
	--cmake-opt=-DCMAKE_INSTALL_PREFIX=%{_libdir}/intel-llvm \
	--cmake-opt=-DCMAKE_INSTALL_LIBDIR=lib \
	--cmake-opt=-DLLVM_PARALLEL_LINK_JOBS=2 \
	--cmake-opt=-DLLVM_EXTERNAL_SPIRV_HEADERS_SOURCE_DIR=%{_builddir}/spirv-headers-llvm \
	--cmake-opt=-DFETCHCONTENT_SOURCE_DIR_VC-INTRINSICS=%{_builddir}/vc-intrinsics \
	--cmake-opt=-DFETCHCONTENT_SOURCE_DIR_EMHASH=%{_builddir}/emhash \
	--cmake-opt=-DFETCHCONTENT_SOURCE_DIR_UNIFIED-MEMORY-FRAMEWORK=%{_builddir}/umf \
	--cmake-opt=-DFETCHCONTENT_SOURCE_DIR_PARALLEL-HASHMAP=%{_builddir}/parallel-hashmap \
	--cmake-opt=-DL0_COMPUTE_RUNTIME_HEADERS=%{_builddir}/neo-l0-headers \
	--cmake-opt=-DUMF_BUILD_CUDA_PROVIDER=OFF \
	--cmake-opt=-DUMF_BUILD_LIBUMF_POOL_JEMALLOC=OFF \
	--cmake-opt=-DUMF_LEVEL_ZERO_INCLUDE_DIR=%{_includedir}/level_zero \
	--cmake-opt=-DUMF_BUILD_TESTS=OFF \
	--cmake-opt=-DUMF_BUILD_EXAMPLES=OFF \
	--cmake-opt=-DLLVM_HOST_TRIPLE=${_triple} \
	--cmake-opt=-DLLVM_DEFAULT_TARGET_TRIPLE=${_triple} \
	--cmake-opt=-DUSE_DEPRECATED_GCC_INSTALL_PREFIX=ON \
	--cmake-opt=-DGCC_INSTALL_PREFIX=/usr
# Link jobs are several GB each.
cmake --build %{_builddir}/intel-llvm-build --target sycl-toolchain -j${RPM_BUILD_NCPUS:-$(nproc)}

%install
DESTDIR=%{buildroot} cmake --build %{_builddir}/intel-llvm-build --target deploy-sycl-toolchain -j${RPM_BUILD_NCPUS:-$(nproc)}

# deploy installs clang/clang++ inside the prefix. Only expose icx/icpx.
if [ ! -e %{buildroot}%{_libdir}/intel-llvm/bin/icpx ]; then
	ln -sf clang++ %{buildroot}%{_libdir}/intel-llvm/bin/icpx
fi
if [ ! -e %{buildroot}%{_libdir}/intel-llvm/bin/icx ]; then
	ln -sf clang %{buildroot}%{_libdir}/intel-llvm/bin/icx
fi
mkdir -p %{buildroot}%{_bindir}
ln -sf %{_libdir}/intel-llvm/bin/icpx %{buildroot}%{_bindir}/icpx
ln -sf %{_libdir}/intel-llvm/bin/icx %{buildroot}%{_bindir}/icx

mkdir -p %{buildroot}%{_sysconfdir}/ld.so.conf.d
echo "%{_libdir}/intel-llvm/lib" > %{buildroot}%{_sysconfdir}/ld.so.conf.d/intel-llvm.conf

%files
%license LICENSE.TXT
%{_libdir}/intel-llvm/
%{_bindir}/icpx
%{_bindir}/icx
%config(noreplace) %{_sysconfdir}/ld.so.conf.d/intel-llvm.conf
