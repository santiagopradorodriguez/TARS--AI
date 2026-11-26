class VoiceCallPcmProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this._buffer = [];
        this._chunkSize = 1024;
    }

    process(inputs) {
        const input = inputs && inputs[0];
        if (!input || !input[0]) {
            return true;
        }
        const channel = input[0];
        for (let i = 0; i < channel.length; i++) {
            this._buffer.push(channel[i]);
        }
        while (this._buffer.length >= this._chunkSize) {
            const slice = this._buffer.splice(0, this._chunkSize);
            const chunk = new Float32Array(slice);
            this.port.postMessage(chunk, [chunk.buffer]);
        }
        return true;
    }
}

registerProcessor('voice-call-pcm-processor', VoiceCallPcmProcessor);
