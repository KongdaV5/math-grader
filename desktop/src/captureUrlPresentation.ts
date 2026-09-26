export type CaptureUrlPresentation = {
  qrValue: string;
  displayHref: string;
  displayText: string;
};

export function getCaptureUrlPresentation(
  captureUrl: string | null | undefined,
): CaptureUrlPresentation | null {
  if (!captureUrl) return null;
  return {
    qrValue: captureUrl,
    displayHref: captureUrl,
    displayText: captureUrl,
  };
}
