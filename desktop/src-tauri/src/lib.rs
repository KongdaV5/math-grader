use fs2::FileExt;
use serde::Serialize;
use std::fs::{self, File, OpenOptions};
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, State};

struct ServiceState {
    child: Option<Child>,
    instance_lock: Option<File>,
    startup_error: Option<String>,
    managed_by_other_instance: bool,
    log_path: PathBuf,
}

struct LocalServiceProcess(Mutex<ServiceState>);

#[derive(Clone, Serialize)]
struct ServiceDiagnostics {
    running: bool,
    managed_by_other_instance: bool,
    startup_error: Option<String>,
    log_path: String,
}

impl ServiceState {
    fn failed(message: impl Into<String>, log_path: PathBuf) -> Self {
        Self {
            child: None,
            instance_lock: None,
            startup_error: Some(message.into()),
            managed_by_other_instance: false,
            log_path,
        }
    }

    fn stop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        if let Some(lock) = self.instance_lock.take() {
            let _ = lock.unlock();
        }
    }

    fn diagnostics(&mut self) -> ServiceDiagnostics {
        let mut running = false;
        if let Some(child) = self.child.as_mut() {
            match child.try_wait() {
                Ok(None) => running = true,
                Ok(Some(status)) => {
                    self.child.take();
                    self.startup_error
                        .get_or_insert_with(|| format!("本地服务已停止（退出状态：{status}）"));
                }
                Err(error) => {
                    self.startup_error
                        .get_or_insert_with(|| format!("无法检查本地服务状态：{error}"));
                }
            }
        }
        ServiceDiagnostics {
            running,
            managed_by_other_instance: self.managed_by_other_instance,
            startup_error: self.startup_error.clone(),
            log_path: self.log_path.display().to_string(),
        }
    }
}

impl LocalServiceProcess {
    fn stop(&self) {
        if let Ok(mut state) = self.0.lock() {
            state.stop();
        }
    }
}

impl Drop for LocalServiceProcess {
    fn drop(&mut self) {
        if let Ok(state) = self.0.get_mut() {
            state.stop();
        }
    }
}

fn service_root(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    if cfg!(debug_assertions) {
        return PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .map_err(|error| format!("Cannot locate the Math Grader project: {error}"));
    }

    let resources = app
        .path()
        .resource_dir()
        .map_err(|error| format!("Cannot locate app resources: {error}"))?;
    if resources.join("local_service").is_dir() {
        Ok(resources)
    } else {
        Err(format!(
            "Bundled local_service was not found in {}",
            resources.display()
        ))
    }
}

fn bundled_python(resources: &Path) -> Result<PathBuf, String> {
    let python = resources.join("runtime/python/bin/python3.12");
    let manifest = resources.join("runtime/runtime-manifest.json");
    if !python.is_file() {
        return Err(format!(
            "Bundled Python runtime is missing: {}",
            python.display()
        ));
    }
    if !manifest.is_file() {
        return Err(format!(
            "Bundled runtime manifest is missing: {}",
            manifest.display()
        ));
    }
    Ok(python)
}

fn default_data_dir(home: &Path) -> PathBuf {
    home.join("Library/Application Support/MathGrader")
}

fn spawn_local_service(app: &tauri::AppHandle) -> Result<ServiceState, String> {
    let root = service_root(app)?;
    let resources = app
        .path()
        .resource_dir()
        .map_err(|error| format!("Cannot locate app resources: {error}"))?;
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Cannot locate app data directory: {error}"))?;
    let home = app
        .path()
        .home_dir()
        .map_err(|error| format!("Cannot locate home directory: {error}"))?;
    let standard_dir = default_data_dir(&home);
    let data_dir = if let Some(override_dir) = std::env::var_os("MATH_GRADER_DATA_DIR") {
        let path = PathBuf::from(override_dir);
        if !path.is_absolute() {
            return Err("MATH_GRADER_DATA_DIR must be an absolute path".to_string());
        }
        path
    } else if !standard_dir.join("data/math-grader.sqlite3").is_file()
        && app_data_dir.join("math-grader.sqlite3").is_file()
    {
        app_data_dir
    } else {
        standard_dir
    };
    let logs_dir = data_dir.join("logs");
    fs::create_dir_all(&logs_dir)
        .map_err(|error| format!("Cannot create app log directory: {error}"))?;
    let log_path = logs_dir.join("local-service.log");
    let log = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|error| format!("Cannot open local service log: {error}"))?;

    let lock_path = logs_dir.join("local-service.lock");
    let lock = OpenOptions::new()
        .create(true)
        .read(true)
        .write(true)
        .open(lock_path)
        .map_err(|error| format!("Cannot open local service lock: {error}"))?;
    match lock.try_lock_exclusive() {
        Ok(()) => {}
        Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
            return Ok(ServiceState {
                child: None,
                instance_lock: None,
                startup_error: None,
                managed_by_other_instance: true,
                log_path,
            });
        }
        Err(error) => return Err(format!("Cannot acquire local service lock: {error}")),
    }

    let mut command = if cfg!(debug_assertions) {
        let python = std::env::var("MATH_GRADER_PYTHON").unwrap_or_else(|_| "python3".to_string());
        Command::new(python)
    } else {
        Command::new(bundled_python(&resources)?)
    };
    let stdout = log
        .try_clone()
        .map_err(|error| format!("Cannot clone local service log: {error}"))?;
    let mut child_command = command
        .args([
            "-m",
            "local_service",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--data-dir",
        ])
        .arg(&data_dir)
        .env_clear()
        .env("HOME", &home)
        .env("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
        .env("PYTHONNOUSERSITE", "1")
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONUNBUFFERED", "1")
        .env("MATH_GRADER_DATA_DIR", &data_dir)
        .env("MATH_GRADER_APP_VERSION", env!("CARGO_PKG_VERSION"))
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(log));
    if let Some(models_dir) = std::env::var_os("MATH_GRADER_MODELS_DIR") {
        let path = PathBuf::from(models_dir);
        if !path.is_absolute() {
            return Err("MATH_GRADER_MODELS_DIR must be an absolute path".to_string());
        }
        child_command = child_command.env("MATH_GRADER_MODELS_DIR", path);
    }
    if cfg!(debug_assertions) {
        child_command = child_command.current_dir(&root).env("PYTHONPATH", &root);
    } else {
        let python = bundled_python(&resources)?;
        let runtime_dir = resources.join("runtime");
        let python_path = std::env::join_paths([
            resources.as_os_str(),
            runtime_dir.join("site-packages").as_os_str(),
        ])
        .map_err(|error| format!("Cannot configure bundled Python paths: {error}"))?;
        child_command = child_command
            .current_dir(&data_dir)
            .env("PYTHONPATH", python_path)
            .env("MATH_GRADER_RUNTIME_DIR", &runtime_dir)
            .env(
                "MATH_GRADER_RUNTIME_MANIFEST",
                runtime_dir.join("runtime-manifest.json"),
            )
            .env(
                "MATH_GRADER_GIT_SHA",
                manifest_git_sha(&runtime_dir).unwrap_or_default(),
            );
        if !python.is_file() {
            return Err("Bundled Python runtime disappeared before service startup".to_string());
        }
    }

    let child = child_command
        .spawn()
        .map_err(|error| format!("无法启动本地服务：{error}"))?;
    Ok(ServiceState {
        child: Some(child),
        instance_lock: Some(lock),
        startup_error: None,
        managed_by_other_instance: false,
        log_path,
    })
}

fn manifest_git_sha(runtime_dir: &Path) -> Option<String> {
    let value = std::fs::read_to_string(runtime_dir.join("runtime-manifest.json")).ok()?;
    let manifest: serde_json::Value = serde_json::from_str(&value).ok()?;
    manifest.get("git_sha")?.as_str().map(str::to_string)
}

#[tauri::command]
fn service_diagnostics(service: State<'_, LocalServiceProcess>) -> ServiceDiagnostics {
    match service.0.lock() {
        Ok(mut state) => state.diagnostics(),
        Err(_) => ServiceDiagnostics {
            running: false,
            managed_by_other_instance: false,
            startup_error: Some("本地服务状态不可读取。".to_string()),
            log_path: String::new(),
        },
    }
}

#[tauri::command]
fn open_service_logs(service: State<'_, LocalServiceProcess>) -> Result<(), String> {
    let path = service
        .0
        .lock()
        .map_err(|_| "Cannot read local service diagnostics".to_string())?
        .log_path
        .clone();
    Command::new("/usr/bin/open")
        .arg(&path)
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("无法打开服务日志：{error}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            service_diagnostics,
            open_service_logs
        ])
        .setup(|app| {
            let fallback_log = app
                .path()
                .home_dir()
                .map(|home| default_data_dir(&home).join("logs/local-service.log"))
                .unwrap_or_else(|_| PathBuf::from("local-service.log"));
            let state = spawn_local_service(app.handle())
                .unwrap_or_else(|message| ServiceState::failed(message, fallback_log));
            app.manage(LocalServiceProcess(Mutex::new(state)));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while running Math Grader desktop app");
    app.run(|app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            app_handle.state::<LocalServiceProcess>().stop();
        }
    });
}

#[cfg(test)]
mod tests {
    use super::{bundled_python, ServiceState};
    use fs2::FileExt;
    use std::fs::{self, OpenOptions};
    use std::path::PathBuf;
    use std::process::Command;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn unique_temp_dir() -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!(
            "math-grader-runtime-test-{}-{stamp}",
            std::process::id()
        ))
    }

    #[test]
    fn packaged_runtime_resolves_only_inside_app_resources() {
        let root = unique_temp_dir();
        let python = root.join("runtime/python/bin/python3.12");
        let manifest = root.join("runtime/runtime-manifest.json");
        fs::create_dir_all(python.parent().unwrap()).unwrap();
        fs::write(&python, "bundled-python").unwrap();
        fs::write(&manifest, "{}").unwrap();
        assert_eq!(bundled_python(&root).unwrap(), python);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn missing_bundled_runtime_fails_without_system_python_fallback() {
        let root = unique_temp_dir();
        let error = bundled_python(&root).unwrap_err();
        assert!(error.contains("Bundled Python runtime is missing"));
        assert!(!error.contains("/usr/bin/python3"));
    }

    #[test]
    fn runtime_lock_prevents_a_second_service_owner() {
        let root = unique_temp_dir();
        fs::create_dir_all(&root).unwrap();
        let lock_path = root.join("local-service.lock");
        let first = OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .open(&lock_path)
            .unwrap();
        let second = OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .open(&lock_path)
            .unwrap();
        first.try_lock_exclusive().unwrap();
        assert!(second.try_lock_exclusive().is_err());
        first.unlock().unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn app_shutdown_reaps_the_managed_service_process() {
        let root = unique_temp_dir();
        let child = Command::new("/bin/sleep").arg("30").spawn().unwrap();
        let mut state = ServiceState {
            child: Some(child),
            instance_lock: None,
            startup_error: None,
            managed_by_other_instance: false,
            log_path: root.join("local-service.log"),
        };
        state.stop();
        assert!(state.child.is_none());
    }
}
