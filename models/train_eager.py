import tensorflow as tf
import argparse
from models import utils
import os
from models.textData import TextData
from tqdm import tqdm
from models.model_rl2 import Model
import pickle as p
import numpy as np
from models.model_basic import ModelBasic
from tensorflow.python import debug as tf_debug
from matplotlib import pyplot as plt

class Train:
	def __init__(self):
		self.args = None

		self.textData = None
		self.model = None
		self.outFile = None
		self.sess = None
		self.saver = None
		self.model_name = None
		self.model_path = None
		self.globalStep = 0
		self.summaryDir = None
		self.testOutFile = None
		self.summaryWriter = None
		self.mergedSummary = None


	@staticmethod
	def parse_args(args):
		parser = argparse.ArgumentParser()

		parser.add_argument('--resultDir', type=str, default='result', help='result directory')
		parser.add_argument('--testDir', type=str, default='test_result')
		# data location
		dataArgs = parser.add_argument_group('Dataset options')

		dataArgs.add_argument('--summaryDir', type=str, default='summaries')
		dataArgs.add_argument('--datasetName', type=str, default='dataset', help='a TextData object')

		dataArgs.add_argument('--dataDir', type=str, default='data', help='dataset directory, save pkl here')
		dataArgs.add_argument('--dataset', type=str, default='rotten')
		dataArgs.add_argument('--trainFile', type=str, default='train.txt')
		dataArgs.add_argument('--valFile', type=str, default='val.txt')
		dataArgs.add_argument('--testFile', type=str, default='test.txt')
		dataArgs.add_argument('--embeddingFile', type=str, default='glove.840B.300d.txt')
		dataArgs.add_argument('--vocabSize', type=int, default=-1, help='vocab size, use the most frequent words')

		# neural network options
		nnArgs = parser.add_argument_group('Network options')
		nnArgs.add_argument('--embeddingSize', type=int, default=300)
		nnArgs.add_argument('--hiddenSize', type=int, default=200, help='hiddenSize for RNN sentence encoder')
		nnArgs.add_argument('--rnnLayers', type=int, default=1)
		nnArgs.add_argument('--maxSteps', type=int, default=50)
		nnArgs.add_argument('--numClasses', type=int, default=2)
		nnArgs.add_argument('--skim', action='store_true')
		# training options
		trainingArgs = parser.add_argument_group('Training options')
		trainingArgs.add_argument('--modelPath', type=str, default='saved')
		trainingArgs.add_argument('--preEmbedding', action='store_true')
		trainingArgs.add_argument('--dropOut', type=float, default=1.0, help='dropout rate for RNN (keep prob)')
		trainingArgs.add_argument('--learningRate', type=float, default=0.001, help='learning rate')
		trainingArgs.add_argument('--batchSize', type=int, default=32, help='batch size')
		trainingArgs.add_argument('--skimloss', action='store_true', help='whether or not to encourage skimming')
		trainingArgs.add_argument('--minRead', type=int, default=2)
		trainingArgs.add_argument('--maxSkip', type=int, default=5)
		trainingArgs.add_argument('--discount', type=float, default=0.99)
		# max_grad_norm
		## do not add dropOut in the test mode!
		trainingArgs.add_argument('--epochs', type=int, default=40, help='most training epochs')
		trainingArgs.add_argument('--device', type=str, default='/gpu:0', help='use the first GPU as default')
		trainingArgs.add_argument('--loadModel', action='store_true', help='whether or not to use old models')
		trainingArgs.add_argument('--testModel', action='store_true')
		trainingArgs.add_argument('--printgate', action='store_true')
		trainingArgs.add_argument('--nSamples', type=int, default=3)
		trainingArgs.add_argument('--eps', type=float, default=0.1)
		return parser.parse_args(args)

	def main(self, args=None):
		print('TensorFlow version {}'.format(tf.VERSION))

		# initialize args
		self.args = self.parse_args(args)

		self.resultDir = os.path.join(self.args.resultDir, self.args.dataset)
		self.summaryDir = os.path.join(self.args.summaryDir, self.args.dataset)
		self.dataDir = os.path.join(self.args.dataDir, self.args.dataset)

		self.outFile = utils.constructFileName(self.args, prefix=self.resultDir)
		self.args.datasetName = utils.constructFileName(self.args, prefix=self.args.dataset, createDataSetName=True)
		datasetFileName = os.path.join(self.dataDir, self.args.datasetName)

		if not os.path.exists(self.resultDir):
			os.makedirs(self.resultDir)

		if not os.path.exists(self.args.modelPath):
			os.makedirs(self.args.modelPath)

		if not os.path.exists(self.summaryDir):
			os.makedirs(self.summaryDir)

		if not os.path.exists(datasetFileName):
			self.textData = TextData(self.args)
			with open(datasetFileName, 'wb') as datasetFile:
				p.dump(self.textData, datasetFile)
			print('dataset created and saved to {}'.format(datasetFileName))
		else:
			with open(datasetFileName, 'rb') as datasetFile:
				self.textData = p.load(datasetFile)
			print('dataset loaded from {}'.format(datasetFileName))

		sessConfig = tf.ConfigProto(allow_soft_placement=True)
		sessConfig.gpu_options.allow_growth = True

		self.modelPath = os.path.join(self.args.modelPath, self.args.dataset)
		self.model_path = utils.constructFileName(self.args, prefix=self.modelPath, tag='model')
		if not os.path.exists(self.model_path):
			os.makedirs(self.model_path)
		self.model_name = os.path.join(self.model_path, 'model')

		self.sess = tf.Session(config=sessConfig)
		# summary writer
		self.summaryDir = utils.constructFileName(self.args, prefix=self.summaryDir)

		with tf.device(self.args.device):
			if self.args.skim:
				print('Skim model created')
				self.model = Model(self.args, self.textData)
			else:
				print('Ordinary model created!')
				self.model = ModelBasic(self.args, self.textData)

			# saver can only be created after we have the model
			self.saver = tf.train.Saver()

			self.summaryWriter = tf.summary.FileWriter(self.summaryDir, self.sess.graph)
			self.mergedSummary = tf.summary.merge_all()

			if self.args.loadModel:
				# load model from disk
				if not os.path.exists(self.model_path):
					print('model does not exist on disk!')
					print(self.model_path)
					exit(-1)

				self.saver.restore(sess=self.sess, save_path=self.model_name)
				print('Variables loaded from disk {}'.format(self.model_name))
			else:
				init = tf.global_variables_initializer()
				# initialize all global variables
				self.sess.run(init)
				print('All variables initialized')

			if not self.args.testModel:
				self.train(self.sess)
			else:
				self.testModel(self.sess)

	def train(self, sess):
		#sess = tf_debug.LocalCLIDebugWrapperSession(sess)

		print('Start training')

		out = open(self.outFile, 'w', 1)
		out.write(self.outFile + '\n')
		utils.writeInfo(out, self.args)

		current_valAcc = 0.0

		for e in range(self.args.epochs):
			# training
			#trainBatches = self.textData.train_batches
			trainBatches = self.textData.get_batches(tag='train')
			totalTrainLoss = 0.0

			# cnt of batches
			cnt = 0

			total_samples = 0
			total_corrects = 0
			all_skip_rate = []
			for idx, nextBatch in enumerate(tqdm(trainBatches)):
				cnt += 1
				#nextBatch = trainBatches[227]
				self.globalStep += 1

				total_samples += nextBatch.batch_size

				py = tf.contrib.eager.py_func(self.model.buildNetwork())

				ops, feed_dict, length = self.model.step(nextBatch, test=False)

				sess.run(py, feed_dict=feed_dict)

				# skip_rate: batch_size * n_samples
				_, loss, predictions, corrects, skip_rate = sess.run(ops, feed_dict)
				all_skip_rate.extend(skip_rate.tolist())
				#print(loss, idx)
				total_corrects += corrects
				totalTrainLoss += loss

				self.summaryWriter.add_summary(utils.makeSummary({"train_loss": loss}), self.globalStep)

			trainAcc = total_corrects * 1.0 / (total_samples*self.args.nSamples)
			train_skip_rate = np.average(all_skip_rate)
			print('\nepoch = {}, Train, loss = {}, trainAcc = {}, train_skip_rate = {}'.
			      format(e, totalTrainLoss, trainAcc, train_skip_rate))

			#continue
			out.write('\nepoch = {}, loss = {}, trainAcc = {}, train_skip_rate = {}\n'.
			          format(e, totalTrainLoss, trainAcc, train_skip_rate))
			out.flush()

			valAcc, valLoss, val_skip_rate = self.test(sess, tag='val')
			testAcc, testLoss, test_skip_rate = self.test(sess, tag='test')

			print('\tVal, loss = {}, valAcc = {}, val_skip_rate = {}'.
			      format(valLoss, valAcc, val_skip_rate))
			out.write('\tVal, loss = {}, valAcc = {}, val_skip_rate = {}\n'.
			          format(valLoss, valAcc, val_skip_rate))

			print('\tTest, loss = {}, testAcc = {}, test_skip_rate = {}'.
			      format(testLoss, testAcc, test_skip_rate))
			out.write('\tTest, loss = {}, testAcc = {}, test_skip_rate = {}\n'.
			          format(testLoss, testAcc, test_skip_rate))

			self.summaryWriter.add_summary(utils.makeSummary({"train_acc": trainAcc}), e)
			self.summaryWriter.add_summary(utils.makeSummary({"val_acc": valAcc}), e)
			self.summaryWriter.add_summary(utils.makeSummary({"test_acc": testAcc}), e)
			self.summaryWriter.add_summary(utils.makeSummary({"train_skip_rate": train_skip_rate}), e)
			self.summaryWriter.add_summary(utils.makeSummary({"val_skip_rate": val_skip_rate}), e)
			self.summaryWriter.add_summary(utils.makeSummary({"test_skip_rate": test_skip_rate}), e)
			# we do not use cross val currently, just train, then evaluate
			if valAcc >= current_valAcc:
				# with open('skip_train.pkl', 'wb') as f:
				# 	p.dump(all_skip_rate, f)
				current_valAcc = valAcc
				print('New valAcc {} at epoch {}'.format(valAcc, e))
				out.write('New valAcc {} at epoch {}\n'.format(valAcc, e))
				save_path = self.saver.save(sess, save_path=self.model_name)
				print('model saved at {}'.format(save_path))
				out.write('model saved at {}\n'.format(save_path))

			out.flush()
		out.close()

	def test(self, sess, tag='val'):
		if tag == 'val':
			print('Validating\n')
			batches = self.textData.val_batches
		else:
			print('Testing\n')
			batches = self.textData.test_batches

		cnt = 0

		total_samples = 0
		total_corrects = 0
		total_loss = 0.0
		all_predictions = []
		all_skip_rate = []
		for idx, nextBatch in enumerate(tqdm(batches)):
			cnt += 1

			total_samples += nextBatch.batch_size
			ops, feed_dict, length = self.model.step(nextBatch, test=True)

			loss, predictions, corrects, skip_rate = sess.run(ops, feed_dict)
			all_skip_rate.extend(skip_rate)
			all_predictions.extend(predictions)
			total_loss += loss
			total_corrects += corrects

			total_length = np.sum(length)

		# plt.hist(all_skip_rate)
		# plt.savefig('tmp.png')
		# print(np.average(all_skip_rate))

		acc = total_corrects * 1.0 / total_samples
		return acc, total_loss, np.average(all_skip_rate)


	def testModel(self, sess):
		acc, total_loss, _ = self.test(sess, tag='test')
		print('acc = {}, total_loss = {}'.format(acc, total_loss))
