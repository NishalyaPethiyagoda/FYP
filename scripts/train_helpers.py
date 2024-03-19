import numpy as np
import tensorflow as tf
import io
import warnings

from glob import glob
from os import remove
from os.path import join
from PIL import Image
from keras.callbacks import Callback


def transform_image(img):
    """
    Convert a numpy representation image to Image protobuf
    """
    height, width = img.shape[:2]
    num_channels = 1 if len(img.shape) < 3 else img.shape[-1]
    image = Image.fromarray(np.squeeze(img).astype(np.uint8))

    output = io.BytesIO()
    image.save(output, format='PNG')
    image_string = output.getvalue()
    output.close()

    # return tf.summary.image(height=height,
    #                         width=width,
    #                         colorspace=num_channels,
    #                         encoded_image_string=image_string)

#added part
    # Decode the image string
    image_tensor = tf.image.decode_png(image_string, channels=num_channels)
    # Reshape if necessary
    if num_channels > 1:
        image_tensor = tf.reshape(image_tensor, (height, width, num_channels))

    return image_tensor

    


class TensorBoardImages(Callback):
    """
    Visualize images and their predictions at every `vis_every` epoch
    """
    def __init__(self, logdir, imgss, vis_every=1):
        super().__init__()
        self.logdir = logdir
        self.imgss = imgss
        self.vis_every = vis_every
        self.writer = tf.summary.create_file_writer(logdir)


    def on_epoch_end(self, epoch, logs=None):
        if epoch % self.vis_every == 0:

            # Create tensorflow summaries for images
            for dataset, imgs in self.imgss.items():
                for i, img in enumerate(imgs):
                    orig = np.squeeze(img)
                    pred = np.squeeze(self.model.predict(np.expand_dims(img, axis=0)))

                    orig_summary = tf.summary.image('Original_{}_{}'.format(dataset, i), transform_image(orig), step=epoch)
                    pred_summary = tf.summary.image('Predicted_{}_{}'.format(dataset, i), transform_image(pred), step=epoch)

                    # Write the summaries to the file writer
                    tf.summary.scalar('Epoch', epoch, step=epoch)
                    tf.summary.histogram('Original_{}_{}'.format(dataset, i), orig, step=epoch)
                    tf.summary.histogram('Predicted_{}_{}'.format(dataset, i), pred, step=epoch)

                    self.writer.flush()  # Flush to write summaries to disk

    def on_train_end(self):
        self.writer.close()
            
            
class CustomModelCheckpoint(Callback):
    """
    Save the last and best weights as well as the complete model according to the monitored metric
    """
    def __init__(self, logdir, monitor='val_loss', verbose=0, save_weights_only=False, mode='auto', period=1):

        super().__init__()
        self.monitor = monitor
        self.verbose = verbose
        self.logdir = logdir
        self.weights_path = join(
            logdir, '{savetype}_{filetype}_epoch-{epoch:04d}_train_loss-{loss:.6f}_val_loss-{val_loss:.6f}.hdf5')
        self.save_weights_only = save_weights_only
        self.period = period
        self.epochs_since_last_save = 0

        if mode not in ['auto', 'min', 'max']:
            warnings.warn('ModelCheckpoint mode %s is unknown, '
                          'fallback to auto mode.' % (mode),
                          RuntimeWarning)
            mode = 'auto'

        if mode == 'min':
            self.monitor_op = np.less
            self.best = np.Inf
        elif mode == 'max':
            self.monitor_op = np.greater
            self.best = -np.Inf
        else:
            if 'acc' in self.monitor or self.monitor.startswith('fmeasure'):
                self.monitor_op = np.greater
                self.best = -np.Inf
            else:
                self.monitor_op = np.less
                self.best = np.Inf
            
    def on_epoch_end(self, epoch, logs=None):
        logs = logs or {}
        self.epochs_since_last_save += 1

        if self.epochs_since_last_save >= self.period:
            self.epochs_since_last_save = 0

            current = logs.get(self.monitor)
            if current is None:
                warnings.warn('Can save best model only with %s available, '
                              'skipping.' % (self.monitor), RuntimeWarning)
            else:
                if self.monitor_op(current, self.best):
                    if self.verbose > 0:
                        print('\nEpoch %05d: %s improved from %0.5f to %0.5f' % (
                            epoch + 1, self.monitor, self.best, current))
                    self.best = current
                    
                    for ckpt_file in glob(join(self.logdir, 'best_weights*')):
                        remove(ckpt_file)
                    self.model.save_weights(
                        self.weights_path.format(savetype='best', filetype='weights', epoch=epoch + 1, **logs))
                    
                    if not self.save_weights_only:
                        for ckpt_file in glob(join(self.logdir, 'best_model*')):
                            remove(ckpt_file)
                        self.model.save(
                            self.weights_path.format(savetype='best', filetype='model', epoch=epoch + 1, **logs))
                else:
                    if self.verbose > 0:
                        print('\nEpoch %05d: %s did not improve from %0.5f' %
                              (epoch + 1, self.monitor, self.best))

            
            for ckpt_file in glob(join(self.logdir, 'last_weights*')):
                remove(ckpt_file)
            self.model.save_weights(
                self.weights_path.format(savetype='last', filetype='weights', epoch=epoch + 1, **logs))
            if not self.save_weights_only:
                for ckpt_file in glob(join(self.logdir, 'last_model*')):
                    remove(ckpt_file)
                self.model.save(self.weights_path.format(savetype='last', filetype='model', epoch=epoch + 1, **logs))