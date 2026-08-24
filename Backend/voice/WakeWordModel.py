"""
Voice/WakeWordModel.py - ML Wake Word Detection Model
TinyML model architecture with feature extraction and training pipeline.
"""

import os
import json
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from typing import List, Dict, Optional, Tuple, Union
import joblib
from dataclasses import dataclass

from .DSP import DSPPipeline, extract_mfcc, compute_energy, compute_zero_crossing_rate


@dataclass
class WakeWordModelConfig:
    """Configuration for wake word model."""
    model_type: str = "tinyml"  # tinyml, lstm, conv1d
    sample_rate: int = 16000
    n_mfcc: int = 40
    n_mels: int = 80
    frame_length: int = 1024
    hop_length: int = 256
    sequence_length: int = 80  # frames
    n_classes: int = 2  # wake_word vs background
    learning_rate: float = 0.001
    batch_size: int = 32
    epochs: int = 50
    dropout: float = 0.2


class WakeWordModel:
    """
    TinyML wake word model with TensorFlow Lite export.
    Trains on MFCC features for fast inference.
    """

    def __init__(self, config: WakeWordModelConfig = None):
        self.config = config or WakeWordModelConfig()
        self.model = None
        self.dsp_pipeline = DSPPipeline(
            input_rate=self.config.sample_rate,
            target_rate=16000,
            boost_db=12.0,
        )
        self.training_history = None
        self.class_weights = None  # For imbalanced data

    # ── Feature Extraction ─────────────────────────────────────────────────────

    def extract_features(self, audio: np.ndarray) -> np.ndarray:
        """
        Extract MFCC features + energy + ZCR from audio.
        Returns: (n_frames, n_features) array
        """
        # Preprocess with DSP
        if len(audio.shape) > 1:
            audio = audio[:, 0]  # Stereo to mono
        audio = self.dsp_pipeline.process(audio)

        # Extract features
        mfcc = extract_mfcc(
            audio,
            sample_rate=self.config.sample_rate,
            n_mfcc=self.config.n_mfcc,
            n_fft=self.config.frame_length,
            hop_length=self.config.hop_length,
        )
        energy = compute_energy(audio, self.config.frame_length, self.config.hop_length)
        zcr = compute_zero_crossing_rate(audio, self.config.frame_length, self.config.hop_length)

        # Stack features
        features = np.stack([mfcc, energy, zcr], axis=-1)  # (time, n_mfcc + 2)

        # Pad or truncate to sequence_length
        if features.shape[0] < self.config.sequence_length:
            # Pad
            pad_shape = (self.config.sequence_length - features.shape[0], features.shape[1])
            features = np.vstack([np.zeros(pad_shape), features])
        else:
            # Truncate
            features = features[-self.config.sequence_length:]

        return features.astype(np.float32)

    def extract_batch(self, audio_samples: List[np.ndarray]) -> np.ndarray:
        """Extract features from a batch of audio samples."""
        batch = []
        for audio in audio_samples:
            features = self.extract_features(audio)
            batch.append(features)
        return np.stack(batch)  # (batch, sequence_length, n_features)

    def load_data(self, data_dir: str) -> Tuple[np.ndarray, np.ndarray]:
        """
        Load wake word dataset from data_dir.
        Returns: (features, labels) arrays
        """
        print(f"Loading data from: {data_dir}")
        X, y = [], []

        # Collect all .raw files
        for root, dirs, files in os.walk(data_dir):
            for file in files:
                if file.endswith(".raw"):
                    label_dir = os.path.basename(root)
                    is_wake_word = label_dir != "background"  # Assuming background dir

                    # Load audio
                    audio_path = os.path.join(root, file)
                    audio = np.fromfile(audio_path, dtype=np.int16).astype(np.float32) / 32768.0

                    # Extract features
                    features = self.extract_features(audio)

                    X.append(features)
                    y.append(1 if is_wake_word else 0)

        print(f"Loaded {len(X)} samples")
        return np.array(X), np.array(y)

    # ── Model Architecture ───────────────────────────────────────────────────

    def build_model(self) -> tf.keras.Model:
        """Build model architecture based on config."""
        inputs = layers.Input(shape=(self.config.sequence_length, self.config.n_mfcc + 2))

        if self.config.model_type == "tinyml":
            # TinyML: Simple 1D CNN for low latency
            x = layers.Reshape((self.config.sequence_length, self.config.n_mfcc + 2))(inputs)
            x = layers.Conv1D(32, 3, activation="relu", padding="same")(x)
            x = layers.Conv1D(64, 3, activation="relu", padding="same")(x)
            x = layers.GlobalAveragePooling1D()(x)
            x = layers.Dropout(self.config.dropout)(x)
            outputs = layers.Dense(1, activation="sigmoid")(x)

        elif self.config.model_type == "conv1d":
            # 1D CNN with deeper architecture
            x = layers.Conv1D(32, 3, activation="relu", padding="same")(inputs)
            x = layers.BatchNormalization()(x)
            x = layers.Conv1D(64, 3, activation="relu", padding="same")(x)
            x = layers.BatchNormalization()(x)
            x = layers.MaxPooling1D(2)(x)
            x = layers.Dropout(self.config.dropout)(x)
            x = layers.Conv1D(128, 3, activation="relu", padding="same")(x)
            x = layers.GlobalMaxPooling1D()(x)
            x = layers.Dropout(self.config.dropout)(x)
            outputs = layers.Dense(1, activation="sigmoid")(x)

        elif self.config.model_type == "lstm":
            # LSTM for temporal sequences
            x = layers.LSTM(64, return_sequences=True)(inputs)
            x = layers.LSTM(32, return_sequences=False)(x)
            x = layers.Dropout(self.config.dropout)(x)
            outputs = layers.Dense(1, activation="sigmoid")(x)

        else:
            raise ValueError(f"Unknown model type: {self.config.model_type}")

        model = keras.Model(inputs, outputs, name="wake_word_model")
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=self.config.learning_rate),
            loss="binary_crossentropy",
            metrics=["accuracy", tf.keras.metrics.Precision(), tf.keras.metrics.Recall()]
        )

        print("Model built:")
        model.summary()
        return model

    # ── Training ──────────────────────────────────────────────────────────────

    def train(self, data_dir: str, epochs: int = None, batch_size: int = None):
        """Train the wake word model."""
        self.config.epochs = epochs or self.config.epochs
        self.config.batch_size = batch_size or self.config.batch_size

        # Load data
        X, y = self.load_data(data_dir)

        # Split train/val (80/20)
        n_train = int(len(X) * 0.8)
        X_train, y_train = X[:n_train], y[:n_train]
        X_val, y_val = X[n_train:], y[n_train:]

        # Calculate class weights for imbalanced data
        n_wake = np.sum(y_train)
        n_bg = len(y_train) - n_wake
        self.class_weights = {
            0: (len(y_train) - n_wake) / len(y_train),      # background
            1: n_wake / len(y_train)                        # wake_word
        }
        print(f"Class weights: background={self.class_weights[0]:.2f}, wake={self.class_weights[1]:.2f}")

        # Build model
        if self.model is None:
            self.model = self.build_model()

        # Train with early stopping
        callbacks = [
            keras.callbacks.EarlyStopping(
                monitor="val_accuracy",
                patience=10,
                restore_best_weights=True
            ),
            keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss",
                factor=0.5,
                patience=5,
                min_lr=1e-6
            ),
        ]

        print(f"\nTraining model for {self.config.epochs} epochs...")
        self.training_history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=self.config.epochs,
            batch_size=self.config.batch_size,
            class_weight=self.class_weights,
            callbacks=callbacks,
            verbose=1
        )

        # Evaluate
        print("\nEvaluating model...")
        test_loss, test_acc, test_prec, test_rec = self.model.evaluate(X_val, y_val, verbose=0)
        print(f"Test accuracy: {test_acc:.3f}, precision: {test_prec:.3f}, recall: {test_rec:.3f}")

    def predict(self, audio: np.ndarray, threshold: float = 0.7) -> Dict[str, Union[float, bool]]:
        """Predict wake word probability for audio."""
        if self.model is None:
            raise ValueError("Model not trained")

        # Extract features and predict
        features = self.extract_features(audio).reshape(1, self.config.sequence_length, -1)
        proba = float(self.model.predict(features, verbose=0)[0][0])
        is_wake = proba >= threshold

        return {
            "probability": float(proba),
            "is_wake_word": is_wake,
            "threshold": threshold
        }

    # ── Export ─────────────────────────────────────────────────────────────────

    def save(self, output_dir: str):
        """Save model and config to disk."""
        os.makedirs(output_dir, exist_ok=True)

        # Save Keras model
        keras_path = os.path.join(output_dir, "wake_word_model.keras")
        self.model.save(keras_path)

        # Save TensorFlow Lite model (quantized)
        converter = tf.lite.TFLiteConverter.from_keras_model(self.model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        converter.inference_input_type = tf.int8
        converter.inference_output_type = tf.int8

        # Quantize model (need to provide calibration data)
        # For now, save float32 TFLite
        tflite_path = os.path.join(output_dir, "wake_word_model.tflite")
        tflite_model = converter.convert()
        with open(tflite_path, "wb") as f:
            f.write(tflite_model)

        # Save config
        config_path = os.path.join(output_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump({
                "config": self.config.__dict__,
                "model_type": self.config.model_type,
                "training_history": self.training_history.history if self.training_history else None
            }, f, indent=2)

        # Save feature normalizer (mean/std for each feature dimension)
        # TODO: Implement feature normalization if needed

        print(f"Model saved to: {output_dir}")

    def load(self, model_path: str):
        """Load saved model."""
        # Load Keras model
        self.model = keras.models.load_model(model_path)
        print(f"Model loaded from: {model_path}")

    # ─── Real-time inference with wake word detector ─────────────────────────────

    def create_wake_detector(self, sample_rate: int = 44100, frame_ms: int = 80) -> WakeWordDetector:
        """
        Create a real-time wake word detector that buffers audio and uses the ML model.
        """
        from .WakeWord import WakeWordDetector, WakeWordConfig

        class WakeWordMLDetector:
            """Real-time ML-based wake word detector."""

            def __init__(self, ml_model, config: WakeWordConfig):
                self.ml_model = ml_model
                self.config = config
                self.buffer = []
                self.sample_rate = sample_rate
                self.frame_samples = int(sample_rate * frame_ms / 1000)

            def process_frame(self, frame: bytes) -> Optional[bool]:
                """Process audio frame and return True if wake word detected."""
                self.buffer.append(frame)

                # Check if we have enough frames for prediction
                n_frames_needed = self.config.sequence_length
                if len(self.buffer) >= n_frames_needed:
                    # Combine frames into single audio
                    audio_bytes = b''.join(self.buffer[-n_frames_needed:])
                    audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                    # Predict
                    result = self.ml_model.predict(audio)
                    if result["is_wake_word"]:
                        return True

                return None

        # Create detector instance
        wake_config = WakeWordConfig()
        return WakeWordMLDetector(self, wake_config)


# ─── Training script ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Wake Word Model Training")
    print("=" * 50)

    # Model config
    config = WakeWordModelConfig(
        model_type="tinyml",
        sequence_length=64,
        epochs=30,
        batch_size=16,
    )

    # Create model
    model = WakeWordModel(config)

    # Train
    data_dir = "data/wake_words"  # Path to collected data
    if os.path.exists(data_dir):
        model.train(data_dir)

        # Save model
        model.save("models/wake_word")
        print("\nModel training complete!")
    else:
        print(f"Data directory not found: {data_dir}")
        print("Run data collection first.")