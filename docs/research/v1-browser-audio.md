# Browser recording and ASR audio paths for v1

Reviewed: 2026-10-30. Scope: desktop Chrome and Edge, English interface and code, learning content without a fixed language. This is documentation research, not a browser or ASR test. It does not settle interaction design or grading thresholds.

## Verified boundaries

| Question | Primary-source evidence | Consequence for v1 |
| --- | --- | --- |
| What does ASR accept? | MiniMax lists WAV, AIFF, FLAC, ALAC/M4A, MP3, AAC, Opus, and Ogg. WebM is not explicitly listed. Raw PCM is unsupported. Limits are 500 seconds and 50 MB; exceeding them can produce 400 and 413 respectively. Mono 16 kHz or compressed audio is recommended. [MiniMax ASR](https://platform.minimax.cn/docs/api-reference/speech-to-text#body-file) | Opus support does not establish support for every Opus container. Changing a filename or MIME label does not convert a container. Direct WebM upload remains unverified. |
| How can the browser record? | Chrome documents MediaRecorder, `audio/webm`, runtime `isTypeSupported()` checks, and collecting nonempty Blobs. [Chrome recording guide](https://developer.chrome.com/blog/mediarecorder) | A native recording API is available. Browser names alone do not prove a recording MIME is supported; native WAV or Ogg recording must not be assumed. |
| When is the file complete? | The recording specification places final `dataavailable` before `stop`. Individual chunks need not play independently; the complete recording combines all chunks. [MediaStream Recording](https://www.w3.org/TR/mediastream-recording/#dom-mediarecorder-stop) | Wait for final data before uploading. A synchronous return from `stop()` does not mean the file is ready. |

MiniMax explicitly lists 20 supported language codes for its optional HTTP `language` header: `zh`, `yue`, `en`, `ja`, `ko`, `th`, `vi`, `id`, `ms`, `fil`, `ar`, `tr`, `fr`, `de`, `es`, `it`, `pt`, `pl`, `ru`, and `uk`. Omitting the header or sending an empty value enables mixed-language recognition. This establishes documented language support, not arbitrary-language coverage or short-answer recognition accuracy. Language-agnostic learning content and a provider's recognition capabilities remain separate concerns. [MiniMax ASR](https://platform.minimax.cn/docs/api-reference/speech-to-text)

## Minimal candidate paths

The following are engineering inferences, not an adopted implementation:

1. Use `getUserMedia({audio: true})` and MediaRecorder; probe and preserve the actual recording MIME. Investigate WebM/Opus on the target browsers. Upload a complete Blob to the application backend, which holds provider credentials.
2. If a target browser actually records a container/codec combination explicitly accepted by ASR, forward it directly. Playback support alone does not prove recording support.
3. For WebM/Opus, investigate either a server-side FFmpeg remux into Ogg/Opus or conversion into mono 16 kHz PCM WAV. The former preserves compressed audio; the latter offers a common provider input. Both add an FFmpeg executable to the image, without requiring a Python audio-wrapper dependency.

FFmpeg streamcopy can change containers without decoding or re-encoding, but target-container constraints can still make it fail. [FFmpeg streamcopy](https://www.ffmpeg.org/ffmpeg.html#Streamcopy) The official format documentation includes an Ogg muxer; the actual WebM/Opus samples still need conversion tests. [FFmpeg Ogg](https://ffmpeg.org/ffmpeg-formats.html#ogg)

A WAV candidate explicitly selects `-ac 1 -ar 16000 -c:a pcm_s16le`. This combines FFmpeg channel, sample-rate, and codec options; it has not been run against application recordings. [FFmpeg audio options](https://www.ffmpeg.org/ffmpeg.html#Audio-Options) Mono, 16 kHz, 16-bit PCM implies approximately 32,000 payload bytes per second, plus a WAV header: arithmetic, not a measured benchmark.

Browser-side WAV encoding could remove the server conversion executable, but requires additional PCM capture/decoding and WAV packaging. No evidence here establishes that it requires less work than MediaRecorder plus conversion. Labelling a WebM Blob `audio/wav` is not WAV encoding.

## Deployment and failure states

Microphone access requires a secure context and permission. Relevant failures include `NotAllowedError` for permission, `NotFoundError` when no suitable device exists, and `NotReadableError` for hardware or operating-system access problems. [Media Capture](https://www.w3.org/TR/mediacapture-streams/#dom-mediadevices-getusermedia)

HTTPS origins, loopback addresses, and qualifying localhost names can be trustworthy. An ordinary HTTP LAN address used by a friend is not thereby localhost. [Secure Contexts](https://www.w3.org/TR/secure-contexts/#is-origin-trustworthy) Therefore, exposing a Compose port does not establish remote recording support; the deployment decision must identify how trusted HTTPS is supplied.

Recording errors may still be followed by data and stop events. Muted tracks can produce silence, so a nonempty Blob does not prove that speech occurred. [Recording errors and silence](https://www.w3.org/TR/mediastream-recording/#error-handling)

Implementation implications to discuss: retain cancellation/failure state so a stop event cannot accidentally submit a cancelled recording; release microphone tracks on completion, cancellation, or navigation; validate decodability, size, and duration on the backend; clean temporary data. Retry and reveal behavior remain product decisions. Silence, an empty transcript, or a provider failure must not silently become evidence of a wrong vocabulary answer. Conversion also needs bounded execution time and temporary storage; its deployment cost needs measurement in the final image.

## Observable timing boundaries

Within one page, `performance.now()` supplies monotonic elapsed time. It is not a durable calendar timestamp across browser restarts; review dates need a separate server time policy. [High Resolution Time](https://www.w3.org/TR/hr-time-3/#the-performance-interface)

Candidate timestamps are: question ready, Speak pressed, permission resolved, recording started, user pressed stop, file ready, and request completed. Separating them makes it possible to exclude permission and model/network delays from fluency grading. Browser events reveal interaction or recording state, not the exact first or last spoken phoneme; measuring speech boundaries requires additional detection rather than a timer alone.

The user still needs to settle whether thinking time includes speaking, how initial authorization is excluded, and what happens after rerecording or backgrounding the tab. Client-reported elapsed time can be modified; plausibility validation does not establish authenticity. V1 should not claim tamper-proof timing.

## Verification left for implementation

- On the target Chrome/Edge versions and operating systems, probe recording MIME and exercise start, stop, cancel, permission denial, device access failure, silence, very short recordings, and changing cards.
- Confirm actual recording samples survive Ogg/Opus remux or WAV conversion, decode completely, and have acceptable conversion cost in the final image. Direct WebM/Opus acceptance needs a live ASR sample during implementation; none was sent here.
- Test the actual HTTPS origin used by friends; localhost success is insufficient.
- Sample short words and phrases in the intended learning languages, distinguishing ASR errors from knowledge errors.

No application code, dependencies, microphone tests, or paid provider calls were used. Audio-format and language compatibility remain subject to the listed live checks.
