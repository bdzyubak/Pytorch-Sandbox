from sklearn.metrics import accuracy_score

import torch
from torch.optim import AdamW
import lightning as pl

from transformers import DistilBertTokenizer, DistilBertForSequenceClassification, RobertaTokenizer, RobertaModel

from utils.torch_utils import tensor_to_numpy, average_round_metric


# NB: Speed up processing for negligible loss of accuracy. Verify acceptable accuracy for a production use case
torch.set_float32_matmul_precision('medium')
torch.backends.cudnn.allow_tf32 = True


class FineTuneLLM(pl.LightningModule):
    def __init__(self, model, tokenizer, device='cuda:0', learning_rate=1e-6):
        super(FineTuneLLM, self).__init__()
        self.model = model
        self.tokenizer = tokenizer
        self.model.to(device)

        self.learning_rate = learning_rate
        # self.save_hyperparameters()

    def forward(self, input_ids, attention_mask, labels=None):
        return self.model(input_ids, attention_mask=attention_mask, labels=labels)

    def on_train_epoch_start(self):
        self.train_loss = list()
        self.train_acc = list()

    def training_step(self, batch, batch_idx):
        input_ids = batch['input_ids']
        attention_mask = batch['attention_mask']
        labels = batch['labels']
        labels_class = tensor_to_numpy(batch['labels_class'])
        outputs = self.model(input_ids, attention_mask=attention_mask, labels=labels)
        loss = outputs.loss
        preds_batch = tensor_to_numpy(torch.argmax(outputs['logits'], axis=1))
        train_acc_batch = accuracy_score(preds_batch, labels_class)
        self.train_loss.append(tensor_to_numpy(loss))
        self.train_acc.append(train_acc_batch)
        return loss

    def on_train_epoch_end(self):
        self.log('train_loss', average_round_metric(self.train_loss))
        self.log('train_acc', average_round_metric(self.train_acc))

    def on_validation_epoch_start(self):
        self.val_loss = list()
        self.val_acc = list()

    def validation_step(self, batch, batch_idx):
        input_ids = batch['input_ids']
        attention_mask = batch['attention_mask']
        labels = batch['labels']
        labels_class = tensor_to_numpy(batch['labels_class'])
        outputs = self.model(input_ids, attention_mask=attention_mask, labels=labels)
        preds_batch = tensor_to_numpy(torch.argmax(outputs['logits'], axis=1))
        val_acc_batch = accuracy_score(preds_batch, labels_class)
        loss = outputs.loss
        self.val_loss.append(tensor_to_numpy(loss))
        self.val_acc.append(val_acc_batch)
        return loss

    def on_validation_epoch_end(self) -> None:
        self.log('val_loss', average_round_metric(self.val_loss))
        self.log('val_acc', average_round_metric(self.val_acc))

    def configure_optimizers(self):
        optimizer = AdamW(self.parameters(), lr=self.learning_rate)
        return optimizer


# def qc_requested_models_supported(model_names):
#     models_unsupported = list()
#     for model_name in model_names:
#         try:
#             model = FineTuneLLM(num_classes=1, model_name=model_name)
#         except RuntimeError:
#             models_unsupported.append(model_name)
#     if models_unsupported:
#         raise ValueError(f'The following models are not supported {models_unsupported}')


class FineTuneLLM_RobertaBaseGo(FineTuneLLM):
    def __init__(self, num_classes, model_name='SamLowe/roberta-base-go_emotions', tokenizer="FacebookAI/roberta-base",
                 device='cuda:0',
                 learning_rate=1e-6):
        # Same as BERT but with better pretraining tricks
        if model_name == 'SamLowe/roberta-base-go_emotions':
            model = RobertaModel.from_pretrained(model_name, num_labels=num_classes)
        else:
            raise NotImplementedError()

        if tokenizer == "FacebookAI/roberta-base":
            tokenizer = RobertaTokenizer.from_pretrained(tokenizer)
        else:
            raise NotImplementedError()

        super(FineTuneLLM_RobertaBaseGo, self).__init__(device=device, learning_rate=learning_rate, model=model,
                                                        tokenizer=tokenizer)


class FineTuneLLM_Distilbert(FineTuneLLM):
    def __init__(self, num_classes, model_name='distilbert-base-uncased', tokenizer='distilbert-base-uncased',
                 device='cuda:0', learning_rate=1e-6):
        # Lean version of BERT
        if model_name == 'distilbert-base-uncased':
            model = DistilBertForSequenceClassification.from_pretrained(model_name, num_labels=num_classes)
        else:
            raise NotImplementedError()

        if tokenizer == 'distilbert-base-uncased':
            tokenizer = DistilBertTokenizer.from_pretrained(tokenizer)
        else:
            raise NotImplementedError()
        super(FineTuneLLM_Distilbert, self).__init__(device=device, learning_rate=learning_rate, model=model,
                                                     tokenizer=tokenizer)
