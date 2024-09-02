import logging

logger = logging.getLogger(__name__)


class MediaService:
    def add_source(self, source):
        # TODO: Create a service for the video device
        try:
            device = source["device"]

            logger.info(f"Opening video device {device}")

            # media_video0 = MediaPlayer(
            #     device,
            #     format="v4l2",
            #     options={
            #         "framerate": source.get("frame_rate", "30"),
            #         "video_size": source.get("video_size", "640x480"),
            #         "preset": "ultrafast",
            #         "tune": "zerolatency",
            #     },
            # )
        except Exception as e:
            logger.error(f"Error opening video device: {e}")
