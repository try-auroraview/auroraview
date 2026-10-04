//! Self-update command for auroraview-cli
//!
//! Downloads and installs the latest version from GitHub releases.

use anyhow::{anyhow, bail, Context, Result};
use clap::Args;
use console::style;
use indicatif::{ProgressBar, ProgressStyle};
use serde::Deserialize;
use std::env;
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};

/// Self-update command arguments
#[derive(Args, Debug)]
pub struct SelfUpdateArgs {
    /// Target version to install (e.g., "0.3.8"). If not specified, installs latest.
    #[arg(value_name = "VERSION")]
    pub version: Option<String>,

    /// Only check for updates without installing
    #[arg(long)]
    pub check_only: bool,

    /// GitHub token to avoid rate limiting
    #[arg(long, env = "GITHUB_TOKEN")]
    pub token: Option<String>,
}

/// GitHub release information
#[derive(Debug, Deserialize)]
struct Release {
    tag_name: String,
    assets: Vec<Asset>,
    prerelease: bool,
}

/// GitHub release asset
#[derive(Debug, Deserialize)]
struct Asset {
    name: String,
    browser_download_url: String,
    size: u64,
}

const GITHUB_REPO: &str = "try-auroraview/auroraview";
const BINARY_NAME: &str = "auroraview-cli";

/// Run the self-update command
pub fn run_self_update(args: SelfUpdateArgs) -> Result<()> {
    let current_version = env!("CARGO_PKG_VERSION");
    println!(
        "{} Current version: {}",
        style("ℹ").blue(),
        style(current_version).cyan()
    );

    // Get release info
    let release = if let Some(ref version) = args.version {
        get_specific_release(version, args.token.as_deref())?
    } else {
        get_latest_release(args.token.as_deref())?
    };

    // Extract version from tag (auroraview-v0.3.8 -> 0.3.8)
    let target_version = release
        .tag_name
        .strip_prefix("auroraview-v")
        .unwrap_or(&release.tag_name);

    println!(
        "{} Latest version: {}{}",
        style("ℹ").blue(),
        style(target_version).cyan(),
        if release.prerelease {
            style(" (prerelease)").yellow().to_string()
        } else {
            String::new()
        }
    );

    // Compare versions
    if current_version == target_version {
        println!(
            "{} You are already running the latest version!",
            style("✓").green()
        );
        return Ok(());
    }

    let is_upgrade = is_newer_version(target_version, current_version);
    if is_upgrade {
        println!(
            "{} New version available: {} -> {}",
            style("↑").green(),
            style(current_version).red(),
            style(target_version).green()
        );
    } else {
        println!(
            "{} Downgrading: {} -> {}",
            style("↓").yellow(),
            style(current_version).cyan(),
            style(target_version).yellow()
        );
    }

    if args.check_only {
        return Ok(());
    }

    // Find the appropriate asset for this platform
    let asset = find_platform_asset(&release.assets, target_version)?;
    println!(
        "{} Downloading: {} ({:.2} MB)",
        style("↓").blue(),
        asset.name,
        asset.size as f64 / 1_000_000.0
    );

    // Download and install
    download_and_install(asset, args.token.as_deref())?;

    println!(
        "{} Successfully updated to version {}!",
        style("✓").green(),
        style(target_version).cyan()
    );

    Ok(())
}

/// Get the latest release from GitHub
fn get_latest_release(token: Option<&str>) -> Result<Release> {
    let url = format!(
        "https://api.github.com/repos/{}/releases/latest",
        GITHUB_REPO
    );
    fetch_release(&url, token)
}

/// Get a specific release by version
fn get_specific_release(version: &str, token: Option<&str>) -> Result<Release> {
    // Try with auroraview-v prefix first
    let tag = if version.starts_with("auroraview-v") || version.starts_with('v') {
        version.to_string()
    } else {
        format!("auroraview-v{}", version)
    };

    let url = format!(
        "https://api.github.com/repos/{}/releases/tags/{}",
        GITHUB_REPO, tag
    );
    fetch_release(&url, token)
}

/// Fetch release info from GitHub API
fn fetch_release(url: &str, token: Option<&str>) -> Result<Release> {
    let client = reqwest::blocking::Client::new();
    let mut request = client.get(url).header(
        "User-Agent",
        format!("{}/{}", BINARY_NAME, env!("CARGO_PKG_VERSION")),
    );

    if let Some(token) = token {
        request = request.header("Authorization", format!("Bearer {}", token));
    }

    let response = request.send().context("Failed to fetch release info")?;

    if !response.status().is_success() {
        if response.status().as_u16() == 404 {
            bail!("Release not found");
        }
        if response.status().as_u16() == 403 {
            bail!(
                "GitHub API rate limit exceeded. Use --token or set GITHUB_TOKEN environment variable."
            );
        }
        bail!("Failed to fetch release: HTTP {}", response.status());
    }

    response.json().context("Failed to parse release info")
}

/// Find the appropriate asset for the current platform
fn find_platform_asset<'a>(assets: &'a [Asset], version: &str) -> Result<&'a Asset> {
    let (os, arch) = get_platform_info();

    // Build expected asset name patterns
    // Format: auroraview-cli-{version}-{platform}.{ext}
    let patterns = match (os, arch) {
        ("windows", "x86_64") => vec![
            format!("auroraview-cli-{}-windows-x64.zip", version),
            "auroraview-cli-windows-x64.zip".to_string(),
        ],
        ("linux", "x86_64") => vec![
            format!("auroraview-cli-{}-linux-x64.tar.gz", version),
            "auroraview-cli-linux-x64.tar.gz".to_string(),
        ],
        ("macos", "x86_64") => vec![
            format!("auroraview-cli-{}-macos-x64.tar.gz", version),
            "auroraview-cli-macos-x64.tar.gz".to_string(),
        ],
        ("macos", "aarch64") => vec![
            format!("auroraview-cli-{}-macos-arm64.tar.gz", version),
            "auroraview-cli-macos-arm64.tar.gz".to_string(),
        ],
        _ => bail!("Unsupported platform: {}-{}", os, arch),
    };

    for pattern in &patterns {
        if let Some(asset) = assets.iter().find(|a| a.name == *pattern) {
            return Ok(asset);
        }
    }

    // Try partial match
    let platform_suffix = match (os, arch) {
        ("windows", "x86_64") => "windows-x64.zip",
        ("linux", "x86_64") => "linux-x64.tar.gz",
        ("macos", "x86_64") => "macos-x64.tar.gz",
        ("macos", "aarch64") => "macos-arm64.tar.gz",
        _ => bail!("Unsupported platform: {}-{}", os, arch),
    };

    assets
        .iter()
        .find(|a| a.name.contains("auroraview-cli") && a.name.ends_with(platform_suffix))
        .ok_or_else(|| {
            anyhow!(
                "No compatible binary found for {}-{}. Available assets: {:?}",
                os,
                arch,
                assets.iter().map(|a| &a.name).collect::<Vec<_>>()
            )
        })
}

/// Get current platform info
fn get_platform_info() -> (&'static str, &'static str) {
    let os = if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "linux") {
        "linux"
    } else if cfg!(target_os = "macos") {
        "macos"
    } else {
        "unknown"
    };

    let arch = if cfg!(target_arch = "x86_64") {
        "x86_64"
    } else if cfg!(target_arch = "aarch64") {
        "aarch64"
    } else {
        "unknown"
    };

    (os, arch)
}

/// Download and install the update
fn download_and_install(asset: &Asset, token: Option<&str>) -> Result<()> {
    // Download to temp file
    let temp_dir = env::temp_dir();
    let temp_archive = temp_dir.join(&asset.name);

    download_file(
        &asset.browser_download_url,
        &temp_archive,
        asset.size,
        token,
    )?;

    // Extract binary
    let binary_path = extract_binary(&temp_archive)?;

    // Get current executable path
    let current_exe = env::current_exe().context("Failed to get current executable path")?;

    // Create backup
    let backup_path = current_exe.with_extension("bak");
    if backup_path.exists() {
        fs::remove_file(&backup_path).ok();
    }

    // Use self_replace to handle the update (works on Windows with locked files)
    #[cfg(windows)]
    {
        self_replace::self_replace(&binary_path).context("Failed to replace executable")?;
    }

    #[cfg(not(windows))]
    {
        // On Unix, we can directly replace
        fs::copy(&current_exe, &backup_path).context("Failed to create backup")?;
        fs::copy(&binary_path, &current_exe).context("Failed to copy new binary")?;

        // Set executable permission
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = fs::metadata(&current_exe)?.permissions();
            perms.set_mode(0o755);
            fs::set_permissions(&current_exe, perms)?;
        }
    }

    // Cleanup
    fs::remove_file(&temp_archive).ok();
    fs::remove_file(&binary_path).ok();

    Ok(())
}

/// Download a file with progress bar
fn download_file(url: &str, path: &Path, size: u64, token: Option<&str>) -> Result<()> {
    let client = reqwest::blocking::Client::new();
    let mut request = client.get(url).header(
        "User-Agent",
        format!("{}/{}", BINARY_NAME, env!("CARGO_PKG_VERSION")),
    );

    if let Some(token) = token {
        request = request.header("Authorization", format!("Bearer {}", token));
    }

    let mut response = request.send().context("Failed to download file")?;

    if !response.status().is_success() {
        bail!("Download failed: HTTP {}", response.status());
    }

    let pb = ProgressBar::new(size);
    pb.set_style(
        ProgressStyle::default_bar()
            .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {bytes}/{total_bytes} ({eta})")
            .expect("valid progress template")
            .progress_chars("#>-"),
    );

    let mut file = File::create(path).context("Failed to create temp file")?;
    let mut downloaded: u64 = 0;
    let mut buffer = [0u8; 8192];

    loop {
        let bytes_read = response.read(&mut buffer)?;
        if bytes_read == 0 {
            break;
        }
        file.write_all(&buffer[..bytes_read])?;
        downloaded += bytes_read as u64;
        pb.set_position(downloaded);
    }

    pb.finish_with_message("Download complete");
    Ok(())
}

/// Extract binary from archive
fn extract_binary(archive_path: &Path) -> Result<PathBuf> {
    let temp_dir = env::temp_dir().join("auroraview-update");
    if temp_dir.exists() {
        fs::remove_dir_all(&temp_dir).ok();
    }
    fs::create_dir_all(&temp_dir)?;

    let archive_name = archive_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("");

    if archive_name.ends_with(".zip") {
        extract_zip(archive_path, &temp_dir)?;
    } else if archive_name.ends_with(".tar.gz") {
        extract_tar_gz(archive_path, &temp_dir)?;
    } else {
        bail!("Unknown archive format: {}", archive_name);
    }

    // Find the binary
    let binary_name = if cfg!(windows) {
        format!("{}.exe", BINARY_NAME)
    } else {
        BINARY_NAME.to_string()
    };

    let binary_path = temp_dir.join(&binary_name);
    if binary_path.exists() {
        return Ok(binary_path);
    }

    // Search in subdirectories
    for entry in fs::read_dir(&temp_dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_file() && path.file_name().map(|n| n.to_str()) == Some(Some(&binary_name)) {
            return Ok(path);
        }
    }

    bail!("Binary not found in archive")
}

/// Extract ZIP archive
fn extract_zip(archive: &Path, dest: &Path) -> Result<()> {
    let file = File::open(archive)?;
    let mut archive = zip::ZipArchive::new(file)?;

    for i in 0..archive.len() {
        let mut file = archive.by_index(i)?;
        let outpath = dest.join(file.mangled_name());

        if file.name().ends_with('/') {
            fs::create_dir_all(&outpath)?;
        } else {
            if let Some(p) = outpath.parent() {
                if !p.exists() {
                    fs::create_dir_all(p)?;
                }
            }
            let mut outfile = File::create(&outpath)?;
            io::copy(&mut file, &mut outfile)?;
        }
    }

    Ok(())
}

/// Extract tar.gz archive
fn extract_tar_gz(archive: &Path, dest: &Path) -> Result<()> {
    let file = File::open(archive)?;
    let decoder = flate2::read::GzDecoder::new(file);
    let mut archive = tar::Archive::new(decoder);
    archive.unpack(dest)?;
    Ok(())
}

/// Compare versions (simple semver comparison)
fn is_newer_version(new: &str, current: &str) -> bool {
    let parse_version = |v: &str| -> (u32, u32, u32) {
        let parts: Vec<u32> = v.split('.').filter_map(|p| p.parse().ok()).collect();
        (
            parts.first().copied().unwrap_or(0),
            parts.get(1).copied().unwrap_or(0),
            parts.get(2).copied().unwrap_or(0),
        )
    };

    let new_v = parse_version(new);
    let current_v = parse_version(current);

    new_v > current_v
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_newer_version() {
        assert!(is_newer_version("0.3.9", "0.3.8"));
        assert!(is_newer_version("0.4.0", "0.3.8"));
        assert!(is_newer_version("1.0.0", "0.3.8"));
        assert!(!is_newer_version("0.3.8", "0.3.8"));
        assert!(!is_newer_version("0.3.7", "0.3.8"));
    }

    #[test]
    fn test_get_platform_info() {
        let (os, arch) = get_platform_info();
        assert!(!os.is_empty());
        assert!(!arch.is_empty());
    }
}
