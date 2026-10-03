from copy import deepcopy


class FakeProbes:
    def __init__(self):
        self.suppliers = [
            {"id": "larkspur-supplies", "name": "Larkspur Supplies", "aliases": "Larkspur"},
            {"id": "larkspur-logistics", "name": "Larkspur Logistics", "aliases": "Larkspur"},
            {"id": "brightfen-paper", "name": "Brightfen Paper", "aliases": "Brightfen"},
        ]
        self.documents = [
            {"doc_id": "ls-1041", "revision": "1", "supplier_id": "larkspur-supplies",
             "supplier": "Larkspur Supplies", "invoice_number": "LS-1041",
             "issue_date": "2026-09-20", "due_date": "2026-10-20",
             "amount": "100.00", "currency": "INR"},
            {"doc_id": "ls-1042", "revision": "1", "supplier_id": "larkspur-supplies",
             "supplier": "Larkspur Supplies", "invoice_number": "LS-1042",
             "issue_date": "2026-10-02", "due_date": "2026-11-01",
             "amount": "48250.00", "currency": "INR"},
        ]
        self.registered = []
        self.csv = {}

    async def register_suppliers(self):
        return deepcopy(self.suppliers)

    async def portal_invoices(self, supplier_id=None):
        return deepcopy([row for row in self.documents
                         if supplier_id is None or row["supplier_id"] == supplier_id])

    async def portal_document(self, doc_id):
        return deepcopy(next(row for row in self.documents if row["doc_id"] == doc_id))

    async def register_invoices(self, supplier_id=None, due_before=None):
        return deepcopy([row for row in self.registered
                         if (supplier_id is None or row["supplier_id"] == supplier_id)
                         and (due_before is None or row["due_date"] < due_before)])

    async def register_supplier(self, supplier_id):
        return deepcopy(next(row for row in self.suppliers if row["id"] == supplier_id))

    async def workspace_csv(self, path):
        return deepcopy(self.csv.get(path))

    async def approval_recorded(self, run_id):
        return False
