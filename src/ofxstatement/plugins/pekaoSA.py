import csv
from datetime import datetime
import re

from ofxstatement import statement
from ofxstatement.parser import CsvStatementParser
from ofxstatement.plugin import Plugin
from ofxstatement.statement import Statement


class PEKAOSAPlugin(Plugin):
    """Polish PEKAO SA (www.pekao24.pl) raw TXT history plugin
    """

    def get_parser(self, filename):
        # read https://github.com/kedder/ofxstatement#advanced-configuration
        # to set the following settings
        # as PEKAOSA files does not include accout info it's worth to set it
        account_id = "PL" + self.settings.get('account_id', '000000000000000000000000').replace(" ", "")
        # in general following setting should not be overwritten byb settings...
        bank_id = self.settings.get('bank_id', 'PKOPPLPW')
        encoding = self.settings.get('charset', 'cp1250')
        return PEKAOSAParser(open(filename, mode="r", encoding=encoding), bank_id, account_id)

class PEKAOSAParser(CsvStatementParser):
    date_format = "%Y%M%D"

    def __init__(self, fin, bank_id, account_id):
        super().__init__(fin)
        self.statement.bank_id = bank_id
        self.statement.account_id = account_id
        self.statement.currency = 'PLN'
        self.headers = {}
        self.row_num = 0


    def split_records(self):
        # PEKAO SA files seems to be TSV variant aka dialect="excel-tab" tab delimited file saved as .txt
        reader = csv.reader(self.fin, delimiter="\t")

    # regular checking (not archive) account statement structure
    """
    mappings = {"date_user":0, #Data księgowania
                "date": 1, #Data waluty
                "payee": 2, #Szczegóły odbiorcy/nadawcy
                "bank_account_to": 3, #Rachunek odbiorcy/nadawcy OR more generic #refnum - does not exist in PEAKO statements
                "memo": 4, #Tytułem
                "amount": 5, #Kwota operacji
                # "": 6, #Waluta
                # "": 7, #Typ operacji (trntype) - need to map polish terms into TRANSACTION_TYPES
                 }
                 # id - generate_transaction_id
                 # self.account_type = account_type  "CHECKING" by default, optional "SAVINGS" or
                 # trntype
    """

        headers = next(reader)
        for i, header in enumerate(headers):
            self.headers[header] = i
            if header == '#Data księgowania':
                self.mappings['date_user'] = i
            elif header == '#Data waluty':
                self.mappings['date'] = i
            elif header == '#Szczegóły odbiorcy/nadawcy':
                self.mappings['payee'] = i
            elif header == '#Rachunek odbiorcy/nadawcy':
                self.mappings['bank_account_to'] = i
            elif header == '#Tytułem':
                self.mappings['memo'] = i
            elif header == '#Kwota operacji':
                self.mappings['amount'] = i
                #"": 6, #Waluta
                #"": 7, #Typ operacji (trntype) - need to map polish terms into TRANSACTION_TYPES

        return reader

    def parse_record(self, line): #StatementLine

        stmt_line = super().parse_record(line)
        self.row_num += 1

        stmt_line.refnum = str(self.row_num)
        stmt_line.trntype = self.get_type(r)
        if stmt_line.date_user:
            r.date_user = self.parse_datetime(r.date_user)
        if stmt_line.date:
            r.date = self.parse_datetime(r.date)

        # generate transaction id out of available data
        stmt_line.id = statement.generate_transaction_id(stmt_line)
        return stmt_line

"""
'#Szczegóły odbiorcy' needs some cleaning:
if trntype is PRZELEW INTERNET M/B or WPŁATA NA RACHUNEK KARTY
then at the end there is 8 digits of pure "#Rachunek" (=without 2-digits security code from the beginning)
if trntype is TRANSAKCJA KARTĄ PŁATNICZĄ
then at the end is probably POS_id '31109455 000000000135045' + ' *********3001077' <- card number used
"""

    def parse_float(self, value):
        value = value.replace(',', '.')
        return super().parse_float(value)

    def get_value(self, line, header):
        if header in self.headers:
            index = self.headers[header]
            value = line[index]
            if index >= len(line):
                raise ValueError("Cannot find column %s in line of %s items "
                                 % (index, len(line)))
            if value:
                return value.strip()
                # setattr(line, header, value)
        return ''

    @staticmethod
    def get_type(line):
        # Check if it would be worth to recognise more TRANSACTION_TYPES based on #Typ operacji header
        if line.amount > 0:
            return 'DEP' # Check if generic CREDIT would be better
        elif line.amount < 0:
            return 'DEBIT'
        else:
            return 'OTHER'
