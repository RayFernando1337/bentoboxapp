// Web Worker for handling transcription
console.log('Worker script starting...');

let whisper = null;
importScripts('/static/js/lib/transformers.min.js');

// Initialize the pipeline
async function initialize() {
    console.log('Initializing Whisper pipeline...');
    try {
        whisper = await pipeline('automatic-speech-recognition', 'Xenova/whisper-tiny.en', {
            progress_callback: function(progress) {
                if (progress.status === 'progress') {
                    postMessage({
                        status: 'loading',
                        message: `Loading model: ${Math.round(progress.progress * 100)}%`
                    });
                }
            }
        });
        console.log('Whisper pipeline initialized successfully');
    } catch (e) {
        console.error('Failed to initialize Whisper:', e);
        postMessage({ status: 'error', message: 'Failed to load model: ' + e.message });
    }
}

// Handle messages from the main thread
self.onmessage = async function(e) {
    console.log('Worker received message:', e.data);
    const { type, data } = e.data;
    
    if (type === 'start') {
        if (!whisper) {
            console.log('Loading Whisper model...');
            postMessage({ status: 'loading', message: 'Loading Whisper model...' });
            await initialize();
        }
        
        try {
            console.log('Starting transcription...');
            postMessage({ status: 'processing', message: 'Starting transcription...' });
            const result = await whisper(data, {
                chunk_length_s: 30,
                stride_length_s: 5,
                return_timestamps: true,
                callback_function: (progress) => {
                    console.log('Transcription progress:', progress);
                    postMessage({ 
                        status: 'progress', 
                        progress: Math.round(progress * 100) 
                    });
                }
            });
            
            console.log('Transcription complete:', result);
            
            // Format chunks to match server format
            const formattedChunks = result.chunks.map((chunk, i) => ({
                index: i + 1,
                start: chunk.timestamp[0],
                end: chunk.timestamp[1],
                text: chunk.text.trim()
            }));
            
            postMessage({ 
                status: 'complete', 
                text: result.text,
                chunks: formattedChunks
            });
        } catch (error) {
            console.error('Transcription failed:', error);
            postMessage({ 
                status: 'error', 
                message: 'Transcription failed: ' + error.message 
            });
        }
    }
};

console.log('Worker script initialized');
