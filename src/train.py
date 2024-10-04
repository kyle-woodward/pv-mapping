# Imports
import tensorflow as tf
from tensorflow.keras import layers, models, optimizers, losses
from functools import partial
from tensorflow.keras.metrics import categorical_accuracy
from tensorflow.keras import backend as backend
from tensorflow import keras
import argparse
import yaml
import logging
import datetime
import os

# setup logging
logging.basicConfig(
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %I:%M:%S %p",
    level=logging.WARNING,
    filename=os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        f'trainlog_{datetime.datetime.now().strftime("%Y-%m-%d")}.log',
    ),  # add _%H-%M-%S if needbe
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Setup GCP Variables
# PROJECT = 'YOUR-CLOUD-PROJECT'
# # these are all Google Cloud Storage paths, looks like 'gs://bucket/folder/optional-subfolder'
# OUTPUT_DIR = 'gs://YOUR-BUCKET/YOUR-NEW-MODEL-OUTPUT-DIR'
# LOGS_DIR = 'gs://YOUR-BUCKET/YOUR-LOGS-OUTPUT-DIR'
# TRAINING_FOLDER = 'gs://YOUR-BUCKET/YOUR-TRAINING-DATA-FOLDER'
# TESTING_FOLDER = 'gs://YOUR-BUCKET/YOUR-TESTING-DATA-FOLDER'
PROJECT = 'pc511-gambia-training'
# these are all Google Cloud Storage paths, looks like 'gs://bucket/folder/optional-subfolder'
OUTPUT_DIR = 'gs://pv_mapping/model_data/pvmodelv1'
LOGS_DIR = 'gs://pv_mapping/logs'
TRAINING_FOLDER = 'gs://pv_mapping/model_data/shape_256x256/training'
TESTING_FOLDER = 'gs://pv_mapping/model_data/shape_256x256/testing'

# Paths and Dataset Parameters
PROJECT = PROJECT
OUTPUT_DIR = OUTPUT_DIR
LOGS_DIR = LOGS_DIR
TRAINING_PATTERN = f'{TRAINING_FOLDER}/*'
TESTING_PATTERN = f'{TESTING_FOLDER}/*'

# Model and Training Configuration
BANDS = ['R', 'G', 'B']
RESPONSE = ["label"]
FEATURES = BANDS + RESPONSE

BATCH_SIZE = 64
EPOCHS = 10

BUFFER_SIZE = 320 # for data shuffling, should be significantly larger than BATCH_SIZE
optimizer = tf.keras.optimizers.Adam()

# Specify the size and shape of patches expected by the model.
KERNEL_SIZE = 256
KERNEL_SHAPE = [KERNEL_SIZE, KERNEL_SIZE]
COLUMNS = [
  tf.io.FixedLenFeature(shape=KERNEL_SHAPE, dtype=tf.float32) for k in FEATURES
]
FEATURES_DICT = dict(zip(FEATURES, COLUMNS))


def recall_m(y_true, y_pred):
    true_positives = backend.sum(backend.round(backend.clip(y_true * y_pred, 0, 1)))
    possible_positives = backend.sum(backend.round(backend.clip(y_true, 0, 1)))
    recall = true_positives / (possible_positives + backend.epsilon())
    return recall

def precision_m(y_true, y_pred):
    true_positives = backend.sum(backend.round(backend.clip(y_true * y_pred, 0, 1)))
    predicted_positives = backend.sum(backend.round(backend.clip(y_pred, 0, 1)))
    precision = true_positives / (predicted_positives + backend.epsilon())
    return precision

def f1_m(y_true, y_pred):
    precision = precision_m(y_true, y_pred)
    recall = recall_m(y_true, y_pred)
    return 2 * ((precision * recall) / (precision + recall + backend.epsilon()))

def dice_coef(y_true, y_pred, smooth=1):
    y_true_f = backend.flatten(y_true)
    y_pred_f = backend.flatten(y_pred)
    intersection = backend.sum(y_true_f * y_pred_f)
    return (2. * intersection + smooth) / (backend.sum(y_true_f) + backend.sum(y_pred_f) + smooth)

def dice_loss(y_true, y_pred, smooth=1):
    intersection = backend.sum(backend.abs(y_true * y_pred), axis=-1)
    true_sum = backend.sum(backend.square(y_true), -1)
    pred_sum = backend.sum(backend.square(y_pred), -1)
    return 1 - ((2. * intersection + smooth) / (true_sum + pred_sum + smooth))

evaluation_metrics = [categorical_accuracy, f1_m, precision_m, recall_m]

@tf.function
def random_transform(data, label):
    x = tf.random.uniform(())

    if x < 0.10:
        # Apply flip left-right to both data and label
        data = tf.image.flip_left_right(data)
        label = tf.image.flip_left_right(label)
    elif tf.math.logical_and(x >= 0.10, x < 0.20):
        # Apply flip up-down to both data and label
        data = tf.image.flip_up_down(data)
        label = tf.image.flip_up_down(label)
    elif tf.math.logical_and(x >= 0.20, x < 0.30):
        # Apply flip left-right and up-down to both data and label
        data = tf.image.flip_left_right(tf.image.flip_up_down(data))
        label = tf.image.flip_left_right(tf.image.flip_up_down(label))
    elif tf.math.logical_and(x >= 0.30, x < 0.40):
        # Rotate both data and label 90 degrees
        data = tf.image.rot90(data, k=1)
        label = tf.image.rot90(label, k=1)
    elif tf.math.logical_and(x >= 0.40, x < 0.50):
        # Rotate both data and label 180 degrees
        data = tf.image.rot90(data, k=2)
        label = tf.image.rot90(label, k=2)
    elif tf.math.logical_and(x >= 0.50, x < 0.60):
        # Rotate both data and label 270 degrees
        data = tf.image.rot90(data, k=3)
        label = tf.image.rot90(label, k=3)
    else:
        pass

    return data, label


@tf.function
def flip_inputs_up_down(inputs):
    return tf.image.flip_up_down(inputs)

@tf.function
def flip_inputs_left_right(inputs):
    return tf.image.flip_left_right(inputs)

@tf.function
def transpose_inputs(inputs):
    flip_up_down = tf.image.flip_up_down(inputs)
    transpose = tf.image.flip_left_right(flip_up_down)
    return transpose

@tf.function
def rotate_inputs_90(inputs):
    return tf.image.rot90(inputs, k=1)

@tf.function
def rotate_inputs_180(inputs):
    return tf.image.rot90(inputs, k=2)

@tf.function
def rotate_inputs_270(inputs):
    return tf.image.rot90(inputs, k=3)




# Tensorflow setup for GPU
gpus = tf.config.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
    except RuntimeError as e:
        print(e)
def parse_tfrecord(example_proto):
  """The parsing function.
  Read a serialized example into the structure defined by FEATURES_DICT.
  Args:
    example_proto: a serialized Example.
  Returns:
    A dictionary of tensors, keyed by feature name.
  """
  return tf.io.parse_single_example(example_proto, FEATURES_DICT)


def to_tuple(inputs):
    """Function to convert a dictionary of tensors to a tuple of (inputs, outputs).
    Turn the tensors returned by parse_tfrecord into a stack in HWC shape.
    Args:
      inputs: A dictionary of tensors, keyed by feature name.
    Returns:
      A tuple of (inputs, outputs).
    """
    inputsList = [inputs.get(key) for key in FEATURES]
    stacked = tf.stack(inputsList, axis=0)
    # Convert from CHW to HWC
    stacked = tf.transpose(stacked, [1, 2, 0])

    # Extract the label tensor
    label = stacked[:, :, len(BANDS):]

    # Create the complementary label tensor (opposite value)
    opposite_label = 1 - label

    # Concatenate the label and its opposite value
    labels_combined = tf.concat([label, opposite_label], axis=-1)

    return stacked[:, :, :len(BANDS)], labels_combined
    #return stacked[:, :, :len(BANDS)], label

def get_dataset(pattern):
    """Function to read, parse, and format to tuple a set of input tfrecord files.
    Get all the files matching the pattern, parse and convert to tuple.
    Args:
      pattern: A file pattern to match in a Cloud Storage bucket.
    Returns:
      A tf.data.Dataset
    """
    glob = tf.io.gfile.glob(pattern)
    dataset = tf.data.TFRecordDataset(glob, compression_type='GZIP')
    dataset = dataset.map(parse_tfrecord, num_parallel_calls=5)
    dataset = dataset.map(to_tuple, num_parallel_calls=5)

    # Apply random transformations to each pair of data and label in the dataset
    transformed_dataset = dataset.map(lambda data, label: random_transform(data, label),
                          num_parallel_calls=tf.data.experimental.AUTOTUNE)

    # Concatenate the original dataset with the transformed dataset to double the size
    dataset = dataset.concatenate(transformed_dataset)
    return dataset


def get_training_dataset(glob):
  """Get the preprocessed training dataset
  Returns:
  A tf.data.Dataset of training data.
  """
  dataset = get_dataset(glob)
  dataset = dataset.shuffle(BUFFER_SIZE).batch(BATCH_SIZE) #.repeat()
  return dataset

training = get_training_dataset(TRAINING_PATTERN)
testing = get_training_dataset(TESTING_PATTERN)

def conv_block(input_tensor, num_filters):
    encoder = layers.Conv2D(num_filters, (3, 3), padding='same')(input_tensor)
    encoder = layers.BatchNormalization()(encoder)
    encoder = layers.Activation('relu')(encoder)
    encoder = layers.Conv2D(num_filters, (3, 3), padding='same')(encoder)
    encoder = layers.BatchNormalization()(encoder)
    encoder = layers.Activation('relu')(encoder)
    return encoder

def encoder_block(input_tensor, num_filters):
    encoder = conv_block(input_tensor, num_filters)
    encoder_pool = layers.MaxPooling2D((2, 2), strides=(2, 2))(encoder)
    return encoder_pool, encoder

def decoder_block(input_tensor, concat_tensor, num_filters):
    decoder = layers.Conv2DTranspose(num_filters, (2, 2), strides=(2, 2), padding='same')(input_tensor)
    decoder = layers.concatenate([concat_tensor, decoder], axis=-1)
    decoder = layers.BatchNormalization()(decoder)
    decoder = layers.Activation('relu')(decoder)
    decoder = layers.Conv2D(num_filters, (3, 3), padding='same')(decoder)
    decoder = layers.BatchNormalization()(decoder)
    decoder = layers.Activation('relu')(decoder)
    decoder = layers.Conv2D(num_filters, (3, 3), padding='same')(decoder)
    decoder = layers.BatchNormalization()(decoder)
    decoder = layers.Activation('relu')(decoder)
    return decoder

def get_model():
    inputs = layers.Input(shape=[None, None, 3])
    encoder0_pool, encoder0 = encoder_block(inputs, 16)
    encoder1_pool, encoder1 = encoder_block(encoder0_pool, 32)
    encoder2_pool, encoder2 = encoder_block(encoder1_pool, 64)
    encoder3_pool, encoder3 = encoder_block(encoder2_pool, 128)
    encoder4_pool, encoder4 = encoder_block(encoder3_pool, 256)
    center = conv_block(encoder4_pool, 512)

    decoder4 = decoder_block(center, encoder4, 256)
    decoder3 = decoder_block(decoder4, encoder3, 128)
    decoder2 = decoder_block(decoder3, encoder2, 64)
    decoder1 = decoder_block(decoder2, encoder1, 32)
    decoder0 = decoder_block(decoder1, encoder0, 16)
    outputs = layers.Conv2D(2, (1, 1), activation='sigmoid')(decoder0)

    model = models.Model(inputs=[inputs], outputs=[outputs])

    model.compile(
        optimizer=optimizer,
        loss=dice_loss,
        metrics=evaluation_metrics
    )

    return model

# Now, include all the custom objects (metrics and loss functions) in a dictionary
custom_objects_dict = {
    'f1_m': f1_m,
    'precision_m': precision_m,
    'recall_m': recall_m,
    'dice_coef': dice_coef,
    'dice_loss': dice_loss  # Including the custom loss function
}


if __name__ == '__main__':

    # initalize new cli parser
    parser = argparse.ArgumentParser(description="Train a model with a .yml file.")

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="path to .yml file",
    )
    args = parser.parse_args()

    config_file = args.config

    with open(config_file, "r") as file:
        config_data = yaml.safe_load(file)

    # retrieve config parameters
    EXPERIMENT_NAME = config_data["experiment_name"]
    OUTPUT_DIR = config_data["output_dir"]
    SEED = config_data["seed"]
    EPOCHS = config_data["epochs"]
    BATCH_SIZE = config_data["batch_size"]
    BUFFER_SIZE = config_data["buffer_size"]
    # LOSS_FN = config_data["loss_function"]
    EARLY_STOPPING_PATIENCE = config_data["early_stopping_patience"]
    
    os.makedirs(os.path.join(OUTPUT_DIR,EXPERIMENT_NAME), exist_ok=True)
    # LOGS_DIR = 'logs'  # This will be a local path within the Colab environment.
    
    # setup model.fit() callbacks
    file_suffix = f"epochs_{EPOCHS}_batchSize_{BATCH_SIZE}_bufferSize_{BUFFER_SIZE}"#+ # add your name or a unique string to identify your model file
    model_file_path = os.path.join(OUTPUT_DIR,file_suffix+"_bestmodel.keras")
    save_model_callback = tf.keras.callbacks.ModelCheckpoint(
        filepath=model_file_path,
        monitor="val_loss",
        verbose=0,
        save_best_only=True,
        # save_weights_only=True,
        mode="auto",
        save_freq="epoch",
    )
    tb_callback = tf.keras.callbacks.TensorBoard(log_dir=LOGS_DIR, histogram_freq=1)

    callbacks = [tb_callback,save_model_callback]

    # Prepare datasets
    training = get_training_dataset(TRAINING_PATTERN)
    testing = get_training_dataset(TESTING_PATTERN)

    # Initialize and compile model
    model = get_model() # you can train a model from scratch
    # or you can load a pre-trained model and re-train it
    # MODEL_DIR = "gs://undp_elearning/kyle/rice_v2/saved_models/modelv2"
    # model = keras.models.load_model(MODEL_DIR, custom_objects=custom_objects_dict)
    print(model.summary())

    # Model training

    model.fit(
        training,
        validation_data=testing,
        epochs=EPOCHS,
        callbacks=[tf.keras.callbacks.TensorBoard(LOGS_DIR)]
    )

    # Save the trained model
    file_suffix = f"_epoch_{EPOCHS}_batchSize_{BATCH_SIZE}_bufferSize_{BUFFER_SIZE}"#+ # add your name or a unique string to identify your model file
    model.save(OUTPUT_DIR+file_suffix+".keras")
    # model.save(OUTPUT_DIR+file_suffix+".h5") # catches deprecated warning
