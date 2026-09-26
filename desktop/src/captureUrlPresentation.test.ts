import assert from "node:assert/strict";
import test from "node:test";
import { getCaptureUrlPresentation } from "./captureUrlPresentation.ts";

test("QR source and Desktop displayed URL use the same Capture URL", () => {
  const captureUrl = "http://192.168.31.89:8766/capture?t=redacted";
  const presentation = getCaptureUrlPresentation(captureUrl);

  assert.ok(presentation);
  assert.equal(presentation.qrValue, captureUrl);
  assert.equal(presentation.displayHref, captureUrl);
  assert.equal(presentation.displayText, captureUrl);
});

test("inactive Capture Session has no QR or displayed address", () => {
  assert.equal(getCaptureUrlPresentation(null), null);
  assert.equal(getCaptureUrlPresentation(""), null);
});
