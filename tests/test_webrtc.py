"""R9: RTP/SRTP/Opus/VP8 reales exclusivamente entre dos peers de loopback."""

import asyncio
import hashlib
import struct
import subprocess
from fractions import Fraction
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import aioice.ice
from aiortc import AudioStreamTrack, RTCConfiguration, RTCPeerConnection, VideoStreamTrack
from av import AudioFrame, VideoFrame

ROOT = Path(__file__).resolve().parents[1]


class PcmAudio(AudioStreamTrack):
    def __init__(self, pcm):
        super().__init__()
        self.pcm, self.position = pcm, 0

    async def recv(self):
        timed = await super().recv()
        frame = AudioFrame(format="s16", layout="mono", samples=480)
        data = (self.pcm * 2)[self.position : self.position + 960]
        self.position = (self.position + 960) % len(self.pcm)
        frame.planes[0].update(data)
        frame.sample_rate = 24000
        frame.pts = timed.pts * 3
        frame.time_base = Fraction(1, 24000)
        return frame


class SyntheticVideo(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.number = 0

    async def recv(self):
        pts, base = await self.next_timestamp()
        frame = VideoFrame(160, 120, "rgb24")
        color = bytes((25 + (self.number * 13) % 190, 90, 180))
        frame.planes[0].update(color * 160 * 120)
        self.number += 1
        frame.pts, frame.time_base = pts, base
        return frame


class LocalWebRtcTest(IsolatedAsyncioTestCase):
    async def test_opus_video_loopback_and_release(self):
        fixture = await asyncio.to_thread(
            subprocess.run,
            ["node", "ops/rtc_pcm_fixture.cjs"],
            cwd=ROOT,
            capture_output=True,
            check=True,
            timeout=10,
        )
        self.assertEqual(len(fixture.stdout), 120000)
        audio, video = PcmAudio(fixture.stdout), SyntheticVideo()
        left, right = (
            RTCPeerConnection(RTCConfiguration(iceServers=[])),
            RTCPeerConnection(RTCConfiguration(iceServers=[])),
        )
        tasks, received = [], {"audio": [], "video": []}

        async def consume(track):
            for _ in range(12):
                frame = await track.recv()
                if track.kind == "audio":
                    raw = bytes(frame.planes[0])
                    values = struct.unpack("<" + "h" * (len(raw) // 2), raw)
                    received["audio"].append(max(abs(v) for v in values))
                else:
                    received["video"].append(hashlib.sha256(bytes(frame.planes[0])).hexdigest())

        @right.on("track")
        def track_received(track):
            tasks.append(asyncio.create_task(consume(track)))

        left.addTrack(audio)
        left.addTrack(video)
        try:
            # Do not enumerate any configured network interface, STUN or TURN server.
            with patch.object(aioice.ice, "get_host_addresses", return_value=["127.0.0.1"]):
                await left.setLocalDescription(await left.createOffer())
                self.assertIn("127.0.0.1", left.localDescription.sdp)
                await right.setRemoteDescription(left.localDescription)
                await right.setLocalDescription(await right.createAnswer())
                await left.setRemoteDescription(right.localDescription)
                async with asyncio.timeout(15):
                    while len(tasks) < 2:
                        await asyncio.sleep(0.01)
                    await asyncio.gather(*tasks)
            self.assertEqual(left.connectionState, "connected")
            self.assertEqual(len(received["audio"]), 12)
            self.assertGreater(max(received["audio"]), 1000)
            self.assertGreater(len(set(received["video"])), 5)
            stats = await right.getStats()
            streams = [s for s in stats.values() if s.type == "inbound-rtp"]
            self.assertEqual({s.kind for s in streams}, {"audio", "video"})
            self.assertTrue(all(s.packetsReceived >= 12 for s in streams))
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.gather(left.close(), right.close())
            audio.stop()
            video.stop()
        self.assertEqual((left.connectionState, right.connectionState), ("closed", "closed"))
        self.assertEqual((audio.readyState, video.readyState), ("ended", "ended"))
