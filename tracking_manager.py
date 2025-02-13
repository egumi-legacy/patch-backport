# from pymongo import MongoClient
from datetime import datetime
import json
from pathlib import Path

class TrackingManager:
    def __init__(self, config):
        self.config = config
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['patch_adaptation']
        self.collection = self.db['adaptation_records']
        
        # 创建索引
        self.collection.create_index([
            ('commit_sha', 1),
            ('target_version', 1),
            ('timestamp', -1)
        ])

    def record_attempt(self, record_data):
        document = {
            'timestamp': datetime.now(),
            'commit_sha': record_data.get('commit_sha'),
            'patch_url': record_data.get('patch_url'),
            'target_version': record_data.get('target_version'),
            'model_version': record_data.get('model_version', 'unknown'),
            'processing_steps': record_data.get('processing_steps', []),
            'success': record_data.get('success', False),
            'failure_reason': record_data.get('failure_reason', ''),
            'similarity_score': record_data.get('similarity_score', 0.0),
            'context_diff': record_data.get('context_diff', ''),
            'adapted_patch_path': record_data.get('adapted_patch_path', ''),
            'original_patch_path': record_data.get('original_patch_path', ''),
            'evaluation_results': record_data.get('evaluation_results', {})
        }
        return self.collection.insert_one(document).inserted_id

    def get_failure_analysis(self):
        pipeline = [
            {'$match': {'success': False}},
            {'$group': {
                '_id': '$failure_reason',
                'count': {'$sum': 1},
                'examples': {'$push': '$patch_url'}
            }},
            {'$sort': {'count': -1}}
        ]
        return list(self.collection.aggregate(pipeline))

    def generate_adaptation_report(self):
        report = {
            'summary_stats': self._get_summary_stats(),
            'failure_analysis': self.get_failure_analysis(),
            'success_cases': self._get_top_success_cases(),
            'problematic_patches': self._get_recent_failures()
        }
        return report

    def _get_summary_stats(self):
        return {
            'total_attempts': self.collection.count_documents({}),
            'success_rate': self.collection.count_documents({'success': True}) / 
                           self.collection.count_documents({}),
            'average_similarity': self.collection.aggregate([
                {'$group': {'_id': None, 'avg': {'$avg': '$similarity_score'}}}
            ]).next().get('avg', 0)
        }

    def _get_top_success_cases(self):
        return list(self.collection.find(
            {'success': True},
            {'commit_sha': 1, 'patch_url': 1, 'similarity_score': 1}
        ).sort('similarity_score', -1).limit(10))

    def _get_recent_failures(self):
        return list(self.collection.find(
            {'success': False},
            {'commit_sha': 1, 'patch_url': 1, 'failure_reason': 1}
        ).sort('timestamp', -1).limit(10))