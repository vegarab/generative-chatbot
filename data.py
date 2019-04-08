import collections
import string
import json
import os
import re
import nltk

# Set max number of tokens allowed in a sentence.
# Sentences above this limit are completely excluded
# from the training data.
MAX_NUM_TOKENS = os.getenv('MAX_NUM_TOKENS', 50)

# Set the maximum number of utterances to load.
MAX_NUM_UTTERANCES = os.getenv('MAX_NUM_UTTERANCES', 5000)

# If specifified, only tweets from this user name will be used as replies.
TARGET_USER = os.getenv('TARGET_USER', None)

# If set, we attempt to check the quality of utterances.
VERIFY_UTTERANCES = os.getenv('VERIFY_UTTERANCES', True)

# If set, we filter away self-responses.
REMOVE_SELF_REPLIES = os.getenv('REMOVE_SELF_REPLIES', True)

# Special tokens.
START_UTTERANCE = '<u>'
END_UTTERANCE = '</u>'
UNKNOWN_TOKEN = '<unk>'
PAD_TOKEN = '<pad>'


def clean_content(content):
    ''' Cleans the text belonging to a content in the Facebook data. '''
    # Facebook encodes the data in their exports incorrectly. We can work around
    # this error by encoding the data as Latin-1 and decoding again as UTF-8.
    content = content.encode('latin1').decode('utf8')
    # Convert all text to lowercase.
    content = content.lower()
    # Remove all punctuation from text.
    content = re.sub('[{}]'.format(re.escape(string.punctuation)), '', content)
    # Replace newlines with spaces.
    content = re.sub('\n', ' ', content)
    # Return the cleaned content.
    return content


def load_utterances():
    ''' Load a list of utterances from Facebook data. '''
    utterances = []

    # Recursively traverse all directories in the corpus folder.
    for root, subdirs, files in os.walk('corpus'):
        # Traverse all files found in this subdirectory.
        for filename in files:
            # Check if we found a JSON file.
            if filename.endswith('json'):
                # Find the complete file path.
                file_path = os.path.join(root, filename)
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    # Load the data file.
                    data = json.load(f)

                    for message in data.get('messages', []):
                        if 'content' in message:
                            utterances.append({
                                'sender_name': clean_content(message['sender_name']),
                                'content': clean_content(message['content']),
                            })

    return utterances


def wrap_utterance(utterance):
    ''' Wrap an utterance in start and end tags, to detect when
    an entire utterance has been generated by the chatbot. '''
    return [START_UTTERANCE] + utterance + [END_UTTERANCE]


def tokenize(utterance):
    ''' Tokenize and clean an utterance. '''
    # Tokenize the utterance using NLTK.
    tokens = [
        token for sentence in nltk.sent_tokenize(utterance, language='norwegian')
        for token in nltk.word_tokenize(sentence, language='norwegian')[:MAX_NUM_TOKENS]
    ]

    # Return tokenized utterance.
    return tokens


def verify_utterance(tokens):
    ''' Verify the quality of an utterance before including it in the dataset. '''
    return len(tokens) <= MAX_NUM_TOKENS


def get_utterance_pairs():
    ''' Load utterances and split them into questions and answers. '''
    # Load utterances from file.
    utterances = load_utterances()[:MAX_NUM_UTTERANCES]

    # Lists for input utterances with corresponding output utterances.
    input_utterances, target_utterances = [], []

    # Loop through all utterances, starting at the second line.
    for i, utterance in enumerate(utterances[1:], 1):
        # Tokenize input and target utterances.
        input_tokens, target_tokens = map(tokenize, (utterances[i-1]['content'], utterance['content']))

        # Check if both the input and the target utterances are good enough to use.
        if VERIFY_UTTERANCES and not (verify_utterance(input_tokens) and verify_utterance(target_tokens)):
            continue

        # Check that the user of the target message is the target user, if set.
        if TARGET_USER != None and utterance['sender_name'] != TARGET_USER.lower():
            continue

        # If set, we remove self replies from the dataset.
        if REMOVE_SELF_REPLIES and utterances[i-1]['sender_name'] == utterance['sender_name']:
            continue

        # Add input utterance to list.
        input_utterances.append(input_tokens)

        # Add corresponding output utterance.
        target_utterances.append(wrap_utterance(target_tokens))

    return input_utterances, target_utterances


def pad_tokens(tokens, max_length):
    ''' Add padding tokens to the given list of tokens until the max length is reached. '''
    return tokens + [PAD_TOKEN] * (max_length - len(tokens))


def get_word_map(corpus):
    ''' Create mapping between tokens and an unique number for each
    token, and vice versa. '''
    # Find tokens from all utterances in the corpus.
    tokens = set(token for utterance in corpus for token in utterance)

    # Map tokens to an unique number. Assign all unknown
    # tokens to the same value. We use the number 0 for
    # this special token, to allow the use of defaultdict.
    token_to_num = collections.defaultdict(lambda: 0)

    # Add the unknown token for good measure.
    token_to_num[UNKNOWN_TOKEN] = 0

    for i, token in enumerate(tokens, start=1):
        # Add tokens into the dictionary.
        token_to_num[token] = i

    # Inverse mapping which takes numbers back to tokens.
    num_to_token = { i: token for token, i in token_to_num.items() }

    # Map 0 back to the special token.
    num_to_token[0] = UNKNOWN_TOKEN

    # Return both mappings.
    return token_to_num, num_to_token


class TokenMapper():
    def __init__(self, utterances):
        ''' Create a word map for the utterances and add special tokens. '''
        tok2num, num2tok = get_word_map(utterances)

        self.tok2num = tok2num
        self.num2tok = num2tok

        # Add special tokens to the set of available tokens.
        for token in [START_UTTERANCE, END_UTTERANCE, UNKNOWN_TOKEN]:
            self.add_token(token)
    

    def add_token(self, token):
        ''' Adds a new token to the end of the mapper dictionary. '''
        if token not in self.tok2num:
            self.tok2num[token] = len(self.num2tok)
            self.num2tok[len(self.num2tok)] = token