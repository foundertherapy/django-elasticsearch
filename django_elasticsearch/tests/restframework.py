# -*- coding: utf-8 -*-
from django.test import TestCase
from django.conf import settings
from django.db.models.query import QuerySet
from django.test.utils import override_settings

from elasticsearch import Elasticsearch

from django_elasticsearch.tests.models import TestModel
from django_elasticsearch.contrib.restframework import ElasticsearchFilterBackend


es = Elasticsearch(getattr(settings, 'ELASTICSEARCH_URL', 'http://localhost:9200'))


class Fake():
    pass


@override_settings(REST_FRAMEWORK=None)
class EsRestFrameworkTestCase(TestCase):
    urls = 'django_elasticsearch.tests.urls'

    def setUp(self):
        self.model1 = TestModel.objects.create(username='1', first_name='test')
        self.model1.es.do_index()
        self.model2 = TestModel.objects.create(username='2', last_name='test')
        self.model2.es.do_index()
        self.model3 = TestModel.objects.create(username='whatever')
        self.model3.es.do_index()
        TestModel.es.do_update()

        self.fake_request = Fake()
        self.fake_request.QUERY_PARAMS = {'q': 'test'}
        self.fake_request.GET = {'q': 'test'}
        self.fake_view = Fake()
        self.fake_view.action = 'list'
        self.queryset = TestModel.objects.all()

    def tearDown(self):
        es.indices.delete(index='django-test')

    def test_filter_backend(self):
        filter_backend = ElasticsearchFilterBackend()
        queryset = filter_backend.filter_queryset(self.fake_request, self.queryset, self.fake_view)
        
        self.assertTrue(self.model1 in queryset)
        self.assertTrue(self.model2 in queryset)
        self.assertFalse(self.model3 in queryset)

    def test_filter_backend_ordering(self):
        filter_backend = ElasticsearchFilterBackend()
        self.fake_view.ordering = ('-username',)
        queryset = filter_backend.filter_queryset(self.fake_request, self.queryset, self.fake_view)
        self.assertTrue(queryset[0].id, self.model2.id)
        self.assertTrue(queryset[1].id, self.model1.id)
        del self.fake_view.ordering

    def test_filter_backend_no_list(self):
        filter_backend = ElasticsearchFilterBackend()
        self.fake_view.action = 'create'
        queryset = filter_backend.filter_queryset(self.fake_request, self.queryset, self.fake_view)
        # the 'normal' dataflow continues
        self.assertTrue(isinstance(queryset, QuerySet))
        self.fake_view.action = 'list'

    def test_filter_backend_filters(self):
        r = self.client.get('/tests/', {'username': '1'})
        self.assertEqual(r.data['count'], 1)
        self.assertTrue(r.data['results'][0]['id'], self.model1.id)

    def test_pagination(self):
        r = self.client.get('/tests/', {'page': 2, 'page_size':1})
        self.assertEqual(r.data['count'], 3)
        self.assertTrue(r.data['results'][0]['id'], self.model2.id)

    def test_facets(self):
        TestModel.Elasticsearch.default_facets_fields = ['first_name',]
        filter_backend = ElasticsearchFilterBackend()
        s = filter_backend.filter_queryset(self.fake_request, self.queryset, self.fake_view)
        expected = {
            u'first_name': {
                u'_type': u'terms',
                u'total': 1,
                u'terms': [{u'count': 1, u'term': u'test'}],
                u'other': 0,
                u'missing': 2
            }
        }
        self.assertEqual(s.facets, expected)
        TestModel.Elasticsearch.default_facets_fields = None

    def test_faceted_viewset(self):
        TestModel.Elasticsearch.default_facets_fields = ['first_name',]
        r = self.client.get('/tests/', {'q': 'test'})
        self.assertTrue('facets' in r.data)
        TestModel.Elasticsearch.default_facets_fields = None