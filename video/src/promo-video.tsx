import type {CSSProperties} from 'react';
import {
  AbsoluteFill,
  Easing,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

type Manifest = {
  durationSeconds: number;
  markers: {
    welcome: number;
    query: number;
    answer: number;
    followup: number;
    followupAnswer: number;
    citation: number;
  };
};

const azure = '#0078d4';
const ink = '#172033';
const muted = '#607086';
const canvas = '#eef3f8';
const introFrames = 105;
const outroFrames = 150;

const base: CSSProperties = {
  fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  color: ink,
};

const fade = (frame: number, duration: number) =>
  interpolate(frame, [0, 15, duration - 18, duration], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

const AzureMark = ({size = 68}: {size?: number}) => (
  <div
    style={{
      width: size,
      height: size,
      borderRadius: size * 0.22,
      background: azure,
      display: 'grid',
      placeItems: 'center',
      color: 'white',
      boxShadow: '0 18px 44px rgba(0,120,212,.24)',
      fontSize: size * 0.5,
      fontWeight: 800,
    }}
  >
    ✦
  </div>
);

const Intro = () => {
  const frame = useCurrentFrame();
  const rise = interpolate(frame, [0, 28], [36, 0], {
    easing: Easing.out(Easing.cubic),
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{...base, background: canvas, alignItems: 'center', justifyContent: 'center'}}>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(circle at 50% 35%, #ffffff 0, #eef3f8 58%, #e5edf5 100%)'}} />
      <div style={{opacity: fade(frame, introFrames), transform: `translateY(${rise}px)`, textAlign: 'center', zIndex: 1}}>
        <div style={{display: 'flex', justifyContent: 'center', marginBottom: 34}}><AzureMark /></div>
        <div style={{fontSize: 72, lineHeight: 1.04, fontWeight: 760, letterSpacing: -3}}>Azure RAG Console</div>
        <div style={{fontSize: 30, color: muted, marginTop: 22}}>Production-shaped. Grounded. Keyless.</div>
        <div style={{display: 'flex', gap: 14, justifyContent: 'center', marginTop: 44}}>
          {['Azure AI Search', 'Azure OpenAI', 'FastAPI + AG-UI', 'Next.js + CopilotKit'].map((item) => (
            <div key={item} style={{background: '#fff', border: '1px solid #d5e0ea', borderRadius: 999, padding: '13px 21px', fontSize: 18, color: '#42536a', boxShadow: '0 8px 22px rgba(37,62,89,.06)'}}>{item}</div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const featureAt = (seconds: number, manifest: Manifest) => {
  if (seconds >= manifest.markers.citation) return ['Traceable sources', 'Inline citations jump directly to the supporting retrieved chunk.'];
  if (seconds >= manifest.markers.followupAnswer) return ['Context-aware follow-ups', 'The conversation stays grounded across multiple turns.'];
  if (seconds >= manifest.markers.followup) return ['Conversational RAG', 'Ask a natural follow-up without repeating the original context.'];
  if (seconds >= manifest.markers.answer) return ['Grounded answers', 'Hybrid search results stream back with source citations.'];
  if (seconds >= manifest.markers.query) return ['Corpus-derived prompts', 'Start with a useful question generated from the indexed documents.'];
  return ['Production readiness', 'Live Search, OpenAI, document, and indexer health at a glance.'];
};

const AppDemo = ({manifest}: {manifest: Manifest}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const seconds = frame / fps;
  const [title, caption] = featureAt(seconds, manifest);
  const enter = interpolate(frame, [0, 22], [0.94, 1], {easing: Easing.out(Easing.cubic), extrapolateRight: 'clamp'});
  const labelOpacity = interpolate(frame % 120, [0, 10], [0.82, 1], {extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{...base, background: '#dce7f1'}}>
      <div style={{position: 'absolute', inset: 0, opacity: 0.5, backgroundImage: 'linear-gradient(rgba(255,255,255,.72) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.72) 1px, transparent 1px)', backgroundSize: '48px 48px'}} />
      <div style={{position: 'absolute', top: 38, left: 72, right: 72, display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 3}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 16}}>
          <AzureMark size={42} />
          <div style={{fontSize: 24, fontWeight: 720}}>Azure RAG Console</div>
        </div>
        <div style={{fontSize: 17, color: muted}}>Azure-native retrieval augmented generation</div>
      </div>
      <div style={{position: 'absolute', top: 105, left: 250, right: 250, bottom: 150, borderRadius: 24, overflow: 'hidden', background: '#f4f6f8', border: '1px solid rgba(95,120,145,.28)', boxShadow: '0 36px 90px rgba(37,62,89,.24)', transform: `scale(${enter})`}}>
        <OffthreadVideo src={staticFile('capture/app-demo.webm')} muted style={{width: '100%', height: '100%', objectFit: 'contain'}} />
      </div>
      <div style={{position: 'absolute', left: 94, right: 94, bottom: 45, display: 'flex', alignItems: 'center', gap: 22, opacity: labelOpacity}}>
        <div style={{height: 56, width: 6, borderRadius: 99, background: azure}} />
        <div>
          <div style={{fontSize: 25, fontWeight: 750, letterSpacing: -0.4}}>{title}</div>
          <div style={{fontSize: 18, color: muted, marginTop: 4}}>{caption}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Outro = () => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, 26], [0, 1], {easing: Easing.out(Easing.cubic), extrapolateRight: 'clamp'});
  const items = ['Managed identity', 'Hybrid + semantic search', 'Streaming AG-UI', 'Source citations', 'Discussion history', 'Corpus lifecycle'];

  return (
    <AbsoluteFill style={{...base, background: ink, color: '#fff', alignItems: 'center', justifyContent: 'center'}}>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(circle at 50% 15%, rgba(0,120,212,.42), transparent 52%)'}} />
      <div style={{zIndex: 1, textAlign: 'center', opacity: fade(frame, outroFrames), transform: `scale(${0.96 + progress * 0.04})`}}>
        <div style={{display: 'flex', justifyContent: 'center', marginBottom: 30}}><AzureMark size={58} /></div>
        <div style={{fontSize: 56, fontWeight: 760, letterSpacing: -2.2}}>Built for production, not just a prototype.</div>
        <div style={{fontSize: 24, color: '#b9c8d8', marginTop: 18}}>An Azure-native reference implementation for grounded enterprise AI.</div>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, width: 930, margin: '42px auto 0'}}>
          {items.map((item, index) => (
            <div key={item} style={{padding: '17px 20px', border: '1px solid rgba(255,255,255,.16)', background: 'rgba(255,255,255,.07)', borderRadius: 13, fontSize: 18, opacity: interpolate(frame, [24 + index * 5, 38 + index * 5], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}), transform: `translateY(${interpolate(frame, [24 + index * 5, 38 + index * 5], [12, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}px)`}}>{item}</div>
          ))}
        </div>
        <div style={{fontSize: 19, color: '#87c9ff', marginTop: 42}}>github.com · portfolio-ready · reproducible from code</div>
      </div>
    </AbsoluteFill>
  );
};

export const PromoVideo = ({manifest}: {manifest: Manifest}) => {
  const {fps} = useVideoConfig();
  const captureFrames = Math.ceil(manifest.durationSeconds * fps);

  return (
    <AbsoluteFill>
      <Sequence durationInFrames={introFrames}><Intro /></Sequence>
      <Sequence from={introFrames} durationInFrames={captureFrames}><AppDemo manifest={manifest} /></Sequence>
      <Sequence from={introFrames + captureFrames} durationInFrames={outroFrames}><Outro /></Sequence>
    </AbsoluteFill>
  );
};
