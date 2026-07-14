import {Composition} from 'remotion';
import manifest from '../public/capture/manifest.json';
import {PromoVideo} from './promo-video';

const fps = 30;
const introFrames = 105;
const outroFrames = 150;
const captureFrames = Math.ceil(manifest.durationSeconds * fps);

export const VideoRoot = () => (
  <Composition
    id="AzureRagPromo"
    component={PromoVideo}
    durationInFrames={introFrames + captureFrames + outroFrames}
    fps={fps}
    width={1920}
    height={1080}
    defaultProps={{manifest}}
  />
);
