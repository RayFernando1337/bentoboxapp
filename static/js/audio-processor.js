class AudioProcessor {
    constructor() {
        console.log('Initializing AudioProcessor...');
        if (!window.AudioContext && !window.webkitAudioContext) {
            console.error('Web Audio API is not supported in this browser');
            throw new Error('Web Audio API not supported');
        }
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.mediaSource = null;
        this.recorder = null;
        this.chunks = [];
        console.log('AudioProcessor initialized successfully');
    }

    async processFile(file) {
        try {
            console.log('Processing file:', file.name, 'Type:', file.type);
            // Reset state
            this.chunks = [];
            
            // If it's a video file, extract audio
            if (file.type.startsWith('video/')) {
                console.log('Extracting audio from video...');
                return await this.extractAudioFromVideo(file);
            } else if (file.type.startsWith('audio/')) {
                console.log('Compressing audio...');
                return await this.compressAudio(file);
            }
            throw new Error('Unsupported file type: ' + file.type);
        } catch (error) {
            console.error('Error processing file:', error);
            throw error;
        }
    }

    async extractAudioFromVideo(videoFile) {
        console.log('Starting audio extraction from video...');
        return new Promise((resolve, reject) => {
            const video = document.createElement('video');
            video.src = URL.createObjectURL(videoFile);
            console.log('Video element created with source:', video.src);
            
            video.onloadedmetadata = async () => {
                console.log('Video metadata loaded, duration:', video.duration);
                try {
                    const stream = video.captureStream();
                    const audioTrack = stream.getAudioTracks()[0];
                    
                    if (!audioTrack) {
                        throw new Error('No audio track found in video');
                    }

                    const audioStream = new MediaStream([audioTrack]);
                    const compressedAudio = await this.compressAudioStream(audioStream);
                    resolve(compressedAudio);
                } catch (error) {
                    reject(error);
                } finally {
                    URL.revokeObjectURL(video.src);
                }
            };
            
            video.onerror = () => reject(new Error('Error loading video file'));
        });
    }

    async compressAudio(audioFile) {
        const arrayBuffer = await audioFile.arrayBuffer();
        const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
        return await this.compressAudioBuffer(audioBuffer);
    }

    async compressAudioBuffer(audioBuffer) {
        // Create offline context for processing
        const offlineContext = new OfflineAudioContext({
            numberOfChannels: 1, // Convert to mono
            length: audioBuffer.length,
            sampleRate: 16000 // Downsample to 16kHz
        });

        // Create source
        const source = offlineContext.createBufferSource();
        source.buffer = audioBuffer;

        // Create compressor
        const compressor = offlineContext.createDynamicsCompressor();
        compressor.threshold.value = -24;
        compressor.knee.value = 30;
        compressor.ratio.value = 12;
        compressor.attack.value = 0.003;
        compressor.release.value = 0.25;

        // Connect nodes
        source.connect(compressor);
        compressor.connect(offlineContext.destination);

        // Start rendering
        source.start(0);
        const renderedBuffer = await offlineContext.startRendering();

        // Convert to WAV
        return await this.bufferToWav(renderedBuffer);
    }

    async compressAudioStream(stream) {
        return new Promise((resolve, reject) => {
            const options = {
                audioBitsPerSecond: 128000,
                mimeType: 'audio/webm'
            };

            const mediaRecorder = new MediaRecorder(stream, options);
            const chunks = [];

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunks.push(e.data);
            };

            mediaRecorder.onstop = async () => {
                try {
                    const blob = new Blob(chunks, { type: 'audio/webm' });
                    const arrayBuffer = await blob.arrayBuffer();
                    const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
                    const compressedAudio = await this.compressAudioBuffer(audioBuffer);
                    resolve(compressedAudio);
                } catch (error) {
                    reject(error);
                }
            };

            mediaRecorder.onerror = (error) => reject(error);

            // Record for the duration of the stream
            mediaRecorder.start();
            setTimeout(() => mediaRecorder.stop(), 100); // Small delay to ensure data is captured
        });
    }

    async bufferToWav(audioBuffer) {
        // Convert AudioBuffer to WAV format
        const numOfChan = audioBuffer.numberOfChannels;
        const length = audioBuffer.length * numOfChan * 2;
        const buffer = new ArrayBuffer(44 + length);
        const view = new DataView(buffer);
        
        // Write WAV header
        const writeString = (view, offset, string) => {
            for (let i = 0; i < string.length; i++) {
                view.setUint8(offset + i, string.charCodeAt(i));
            }
        };

        writeString(view, 0, 'RIFF');
        view.setUint32(4, 36 + length, true);
        writeString(view, 8, 'WAVE');
        writeString(view, 12, 'fmt ');
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, numOfChan, true);
        view.setUint32(24, audioBuffer.sampleRate, true);
        view.setUint32(28, audioBuffer.sampleRate * 2 * numOfChan, true);
        view.setUint16(32, numOfChan * 2, true);
        view.setUint16(34, 16, true);
        writeString(view, 36, 'data');
        view.setUint32(40, length, true);

        // Write audio data
        const offset = 44;
        const channelData = new Float32Array(audioBuffer.length);
        const volume = 0.8; // Reduce volume slightly to prevent clipping
        
        for (let i = 0; i < audioBuffer.numberOfChannels; i++) {
            audioBuffer.copyFromChannel(channelData, i);
            for (let j = 0; j < channelData.length; j++) {
                const index = offset + (j * 2);
                const sample = Math.max(-1, Math.min(1, channelData[j])) * volume;
                view.setInt16(index, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
            }
        }

        return new Blob([buffer], { type: 'audio/wav' });
    }
}
