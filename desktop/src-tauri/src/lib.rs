use std::fs::{self, OpenOptions};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;

struct LocalServiceProcess(Mutex<Option<Child>>);

impl Drop for LocalServiceProcess {
    fn drop(&mut self) {
        if let Ok(mut child) = self.0.lock() {
            if let Some(process) = child.as_mut() {
                let _ = process.kill();
                let _ = process.wait();
            }
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
        Err(format!("Bundled local_service was not found in {}", resources.display()))
    }
}

fn spawn_local_service(app: &tauri::AppHandle) -> Result<Child, String> {
    let root = service_root(app)?;
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Cannot locate app data directory: {error}"))?;
    fs::create_dir_all(&data_dir).map_err(|error| format!("Cannot create app data directory: {error}"))?;

    let log = OpenOptions::new()
        .create(true)
        .append(true)
        .open(data_dir.join("local-service.log"))
        .map_err(|error| format!("Cannot open local service log: {error}"))?;
    let stdout = log.try_clone().map_err(|error| error.to_string())?;
    let python = std::env::var("MATH_GRADER_PYTHON").unwrap_or_else(|_| "python3".to_string());

    Command::new(&python)
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
        .current_dir(&root)
        .env("PYTHONPATH", &root)
        .env("PYTHONUNBUFFERED", "1")
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(log))
        .spawn()
        .map_err(|error| format!("Cannot start local Python service ({python}): {error}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let child = spawn_local_service(app.handle())
                .map_err(|message| std::io::Error::new(std::io::ErrorKind::Other, message))?;
            app.manage(LocalServiceProcess(Mutex::new(Some(child))));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Math Grader desktop app");
}
