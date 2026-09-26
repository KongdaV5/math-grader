# Use Math Grader

## Open the app

Open **Math Grader.app** from Finder. The app starts its local service automatically. You do not need to install or launch Python, Terminal commands, a virtual environment, or a separate model server.

The current macOS app is for Apple Silicon Macs running macOS 15.0 or newer. Its local build is at `~/Desktop/Math Grader.app`.

## Manage recognition models

Math Grader does not download large models during startup. Open **模型中心** and choose **下载** for the models needed by your work. The app stores those models locally and runs them on the Mac. The Qwen visual model is loaded only when a workflow needs it; opening the app does not load its weights.

If a required model is not installed, the app reports that state in the model or capability status. Formula or visual recognition runtime problems are reported separately from a model that has not been installed.

## Capture and grade an Assignment

1. Create or choose a class and open a new Assignment.
2. Start a Capture Session on the Mac. Connect the iPhone and Mac to the same Wi-Fi, then scan the QR code with the iPhone camera to open the capture page in Safari.
3. Photograph each page, review it, and choose to keep or retake it. Kept pages upload to the Mac immediately. Use the page controls to remove or reorder a page. Confirm **完成该生** only after all pages for the current student are present; the phone then moves to the next student.
4. On the Mac, choose **查看并开始批改** to open the student's Submission Workspace. Check the original page images before starting recognition.
5. Choose an existing workbook when one applies. For a new exam, choose **自动分析本次试卷**, review and edit the proposed question structure, answer regions, and answer key, then confirm the Assignment template once. Later students in that Assignment reuse the confirmed structure.
6. Start answer recognition and grading. Deterministic rules grade supported answer types; items that need teacher judgment appear in Human Review. Resolve those items to complete the student's result.

This workflow runs locally. AI-proposed questions and answers require teacher confirmation, and synthetic-data checks do not establish accuracy on real student handwriting.

## Keep your data

The app stores classes, students, Assignments, submissions, photographs, models, and logs under:

```text
~/Library/Application Support/MathGrader/
```

Replacing or deleting Math Grader.app does not remove this folder. To troubleshoot a startup failure, use **查看日志** in the app or open the `logs` folder from Settings.

All grading data and inference remain local to this Mac. The app does not require an account or a cloud model service.
