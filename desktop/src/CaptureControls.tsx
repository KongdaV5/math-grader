import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import { api, type CaptureSessionSnapshot } from "./api";

type CaptureControlsProps = {
  assignmentId: string;
  assignmentLabel: string;
  serviceReady: boolean;
  onActiveChange: (active: boolean) => void;
};

const statusLabels: Record<string, string> = {
  QUEUED: "排队中",
  RUNNING: "后台处理中",
  PROCESSING: "后台处理中",
  COMPLETED: "处理完成",
  FAILED: "处理失败",
};

export function CaptureControls({ assignmentId, assignmentLabel, serviceReady, onActiveChange }: CaptureControlsProps) {
  const [snapshot, setSnapshot] = useState<CaptureSessionSnapshot | null>(null);
  const [selectedHost, setSelectedHost] = useState("");
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const next = await api.captureSession();
      setSnapshot(next);
      setSelectedHost((current) => {
        if (next.host) return next.host;
        return next.addresses.some((address) => address.ip === current) ? current : next.addresses[0]?.ip ?? "";
      });
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法读取手机拍摄状态");
    }
  }, []);

  useEffect(() => {
    if (!serviceReady) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(timer);
  }, [refresh, serviceReady]);

  const active = snapshot?.status === "ACTIVE" && Boolean(snapshot.capture_url);
  useEffect(() => onActiveChange(active), [active, onActiveChange]);

  useEffect(() => {
    let current = true;
    if (!snapshot?.capture_url) {
      setQrDataUrl("");
      return () => { current = false; };
    }
    void QRCode.toDataURL(snapshot.capture_url, {
      width: 260,
      margin: 2,
      errorCorrectionLevel: "M",
      color: { dark: "#17231b", light: "#ffffff" },
    }).then((dataUrl) => {
      if (current) setQrDataUrl(dataUrl);
    }).catch((cause: unknown) => {
      if (current) setError(cause instanceof Error ? cause.message : "二维码生成失败");
    });
    return () => { current = false; };
  }, [snapshot?.capture_url]);

  async function start() {
    if (!assignmentId || !selectedHost || busy) return;
    setBusy(true);
    setError("");
    try {
      setSnapshot(await api.startCaptureSession(assignmentId, selectedHost));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法开启手机拍摄");
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function end() {
    if (busy || !window.confirm("结束手机拍摄？当前二维码会立即失效。")) return;
    setBusy(true);
    setError("");
    try {
      setSnapshot(await api.endCaptureSession());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "结束手机拍摄失败");
    } finally {
      setBusy(false);
    }
  }

  const capture = snapshot?.capture;

  return (
    <section className="bridge-panel" aria-labelledby="capture-bridge-heading">
      <div className="bridge-heading">
        <div>
          <p className="eyebrow">CAPTURE BRIDGE</p>
          <h3 id="capture-bridge-heading">手机拍摄</h3>
        </div>
        <span className={`status-badge ${active ? "status-capturing" : ""}`}>{active ? "已开启" : "未开启"}</span>
      </div>

      {error && <p className="notice error" role="alert">{error}</p>}

      {!active && <div className="bridge-start">
        <label className="field-label" htmlFor="capture-host">手机连接地址</label>
        <select
          id="capture-host"
          value={selectedHost}
          onChange={(event) => setSelectedHost(event.target.value)}
          disabled={!serviceReady || busy || snapshot?.addresses.length === 0}
        >
          {snapshot?.addresses.map((address) => (
            <option key={address.ip} value={address.ip}>{address.ip} · {address.interface}</option>
          ))}
          {!snapshot?.addresses.length && <option value="">未发现局域网地址</option>}
        </select>
        <p className="bridge-help">
          {snapshot?.addresses.length
            ? `将为「${assignmentLabel || "当前作业"}」开启一次班级拍摄。手机和 Mac 需连接同一 Wi-Fi。`
            : "请先让 Mac 连接 Wi-Fi，再刷新页面。"}
        </p>
        <button
          className="button primary"
          type="button"
          onClick={() => void start()}
          disabled={!serviceReady || busy || !assignmentId || !selectedHost || !snapshot?.addresses.length}
        >
          {busy ? "正在开启…" : "开启手机拍摄"}
        </button>
        {snapshot?.status === "ENDED" && <p className="bridge-help">上一场手机拍摄已结束。</p>}
        {snapshot?.status === "EXPIRED" && <p className="bridge-help">上一场手机拍摄已过期，请重新开启。</p>}
      </div>}

      {active && capture && <div className="bridge-active">
        <p className="bridge-assignment">{capture.class_name} · {capture.assignment_name}</p>
        <div className="bridge-current">
          <div>
            <span className="field-label">当前采集</span>
            {capture.current
              ? <strong>{capture.current.student_name} · {capture.current.page_count} 页</strong>
              : <strong>本班拍摄完成</strong>}
            <small>{capture.finished_count} / {capture.total_students} 名学生已完成</small>
          </div>
          {qrDataUrl && <img className="capture-qr" src={qrDataUrl} alt="手机拍摄二维码，请使用 iPhone 相机扫描" />}
        </div>
        <p className="field-label">手机地址</p>
        <a className="capture-url" href={snapshot.capture_url ?? undefined} target="_blank" rel="noreferrer">
          {snapshot.capture_url}
        </a>
        <div className="bridge-background">
          <span className="field-label">Mac 后台队列</span>
          {capture.processing.length
            ? <ul>{capture.processing.map((item, index) => (
              <li key={`${item.student_name}-${index}`}>
                <span>{item.student_name}</span>
                <strong>{statusLabels[item.job_status ?? item.status] ?? item.status}</strong>
              </li>
            ))}</ul>
            : <p>暂无等待或处理中学生</p>}
        </div>
        <button className="button subtle" type="button" onClick={() => void end()} disabled={busy}>
          {busy ? "正在结束…" : "结束手机拍摄"}
        </button>
      </div>}
    </section>
  );
}
