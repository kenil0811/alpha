use std::path::PathBuf;
use std::process::Command;

fn main() {
    tauri_build::build();
    #[cfg(target_os = "macos")]
    build_stt_helper();
}

/// Compiles `native/stt_helper.swift` (native macOS speech-to-text; see that file for why it's
/// Swift rather than a new Rust dependency tree) into a standalone binary next to the build
/// output, so `speech.rs` can spawn it by a path baked in at compile time (`STT_HELPER_PATH`).
#[cfg(target_os = "macos")]
fn build_stt_helper() {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let source = manifest_dir.join("native/stt_helper.swift");
    println!("cargo:rerun-if-changed={}", source.display());
    let out_dir = PathBuf::from(std::env::var("OUT_DIR").expect("OUT_DIR"));
    let binary = out_dir.join("stt_helper");
    let status = Command::new("swiftc")
        .args(["-O", source.to_str().expect("utf8 path"), "-o", binary.to_str().expect("utf8 path")])
        .status()
        .expect("run swiftc (Xcode command line tools required)");
    if !status.success() {
        panic!("swiftc failed to build native/stt_helper.swift");
    }
    println!("cargo:rustc-env=STT_HELPER_PATH={}", binary.display());
}
