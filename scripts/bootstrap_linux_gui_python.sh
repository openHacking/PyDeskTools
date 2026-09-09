#!/usr/bin/env bash
set -euo pipefail

prefix="${1:?usage: bootstrap_linux_gui_python.sh PREFIX}"
python_version=3.14.6
tk_version=9.0.4
work="$(pwd)/build/linux-gui-sources"
mkdir -p "$work" "$prefix"

if [[ -x "$prefix/bin/python3.14" ]] && \
  "$prefix/bin/python3.14" -c 'import tkinter; assert tkinter.TkVersion >= 9' 2>/dev/null; then
  exit 0
fi

fetch() {
  local url="$1" output="$2" expected="$3"
  if [[ ! -f "$output" ]] || [[ "$(sha256sum "$output" | cut -d' ' -f1)" != "$expected" ]]; then
    rm -f "$output"
    curl --fail --location --retry 3 --output "$output" "$url"
  fi
  echo "$expected  $output" | sha256sum --check --status
}

fetch "https://prdownloads.sourceforge.net/tcl/tcl${tk_version}-src.tar.gz" \
  "$work/tcl-${tk_version}.tar.gz" d0aed49230bc02a65c1e0229e65f34590a4b037ec40d546f32573b467f7551ea
fetch "https://prdownloads.sourceforge.net/tcl/tk${tk_version}-src.tar.gz" \
  "$work/tk-${tk_version}.tar.gz" d7a146d2917eb8b5cc95276dbf0e3d03c7464d2b19c1675357857c989301dbb4
fetch "https://www.python.org/ftp/python/${python_version}/Python-${python_version}.tgz" \
  "$work/Python-${python_version}.tgz" 74d0d71d0600e477651a077101d6e62d1e2e69b8e992ba18c993dd643b7ba222

rm -rf "$work/tcl${tk_version}" "$work/tk${tk_version}" "$work/Python-${python_version}"
tar -xzf "$work/tcl-${tk_version}.tar.gz" -C "$work"
tar -xzf "$work/tk-${tk_version}.tar.gz" -C "$work"
tar -xzf "$work/Python-${python_version}.tgz" -C "$work"

(
  cd "$work/tcl${tk_version}/unix"
  ./configure --prefix="$prefix" --enable-threads --enable-64bit
  make -j"$(nproc)"
  make install
)
(
  cd "$work/tk${tk_version}/unix"
  ./configure --prefix="$prefix" --with-tcl="$prefix/lib" --enable-threads --enable-64bit
  make -j"$(nproc)"
  make install
)
(
  cd "$work/Python-${python_version}"
  export PKG_CONFIG_PATH="$prefix/lib/pkgconfig"
  export LD_LIBRARY_PATH="$prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  LDFLAGS="-Wl,-rpath,$prefix/lib" ./configure --prefix="$prefix" --with-ensurepip=install
  make -j"$(nproc)"
  make install
)

"$prefix/bin/python3.14" -c \
  'import platform, tkinter; assert platform.machine() == "x86_64"; assert tkinter.TkVersion >= 9; print(platform.python_version(), tkinter.TkVersion)'
