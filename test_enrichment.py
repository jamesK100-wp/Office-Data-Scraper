import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrichment import Page, extract, research
import json
from unittest.mock import patch

class EnrichmentTests(unittest.TestCase):
    def page(self, city='Pune', name='Example Gardens'):
        obj={'@type':'ApartmentComplex','name':name,'address':{'addressLocality':city},
             'numberOfAccommodationUnits':120,'amenityFeature':[{'name':'Pool','value':True}],
             'hasFloorPlan':{'numberOfBedrooms':2,'floorSize':{'value':80,'unitCode':'MTK'},
                            'offers':{'price':25000,'priceCurrency':'INR'}}}
        return Page('<script type="application/ld+json">'+json.dumps(obj)+'</script>')
    def test_exact_match_and_no_rental_price(self):
        fields, units=extract(self.page(),'Example Gardens','Pune')
        self.assertEqual(fields['Number of Units'],120)
        self.assertEqual(units[0][1],861.11)
        self.assertIsNone(units[0][2])
    def test_wrong_city_or_project_rejected(self):
        self.assertEqual(extract(self.page(),'Other Gardens','Pune'),({},[]))
        self.assertEqual(extract(self.page(),'Example Gardens','Mumbai'),({},[]))
    def test_unavailable_site_keeps_saved_data(self):
        saved={'fields':{'Number of Units':42},'units':[['2 BHK',800,10000000,'Carpet','Saved']]}
        with patch('enrichment.public_url',side_effect=ValueError()):
            result=research({'place':{'websiteUri':'https://example.com'}},'Pune',saved)
        self.assertEqual(result['fields'],saved['fields'])
        self.assertEqual(result['units'],saved['units'])
        self.assertNotIn('auto_status',saved)

if __name__=='__main__': unittest.main()
