"""Admin bulk-import sample templates, scoped to the selected clinic entity.

Template delivery does not modify patient or financial records. Import/posting
endpoints require separate validation and transaction-safety review.
"""
import csv
from io import BytesIO, StringIO
from fastapi import Depends
from fastapi.responses import StreamingResponse

COMMON = {
    'categories': ['Category Type', 'Category Name', 'Code', 'Default'],
    'staff_doctors': ['Record Type', 'Full Name', 'Username', 'Role', 'Entity'],
    'roles_groups': ['Entity', 'Group Name', 'Permission Codes', 'Staff Username', 'Roles'],
    'patients': ['Patient Name', 'Phone', 'Date of Birth', 'UHID'],
    'opening_balances': ['Patient UHID', 'Opening Outstanding', 'Unallocated Advance', 'Reference', 'Reason'],
    'clinical_templates': ['Shortcut', 'Full Text'],
}
EXAMPLES = {
    'categories': ['Treatment', 'Endodontics', '', ''],
    'staff_doctors': ['Doctor', 'Dr Example', '', '', 'Main Clinic'],
    'roles_groups': ['Main Clinic', 'Front Desk', 'patients.read;patients.write', 'example_user', 'reception'],
    'patients': ['Example Patient', '9000000000', '2000-01-01', ''],
    'opening_balances': ['CL-UHID-000001', '500.00', '100.00', 'MIGRATION-001', 'Verified legacy opening balance'],
    'clinical_templates': ['adv1', 'Advised review after one week.'],
}
TEMPLATE_NOTES = [
    'Instructions',
    'Use a separate file for each entity. Never include real patient information in sample files.',
    'Procedure Name must be first; Treatment Category must be second.',
    'Prices are in Indian Rupees with a maximum of two decimal places.',
    'User and financial imports require elevated validation and authorization.',
    'Preview and approval must precede any live import. A template download alone does not import data.',
]

def register(app,helpers):
    db,access,current,rows=[helpers[k] for k in ('db','access','current','rows')]

    @app.get('/api/entities/{eid}/v4/bulk/template/{kind}')
    def template(eid:int,kind:str,format:str='csv',u=Depends(current)):
        access(eid,u,('admin',))
        if kind not in {'procedures',*COMMON} or format not in ('csv','xlsx'):
            from fastapi import HTTPException
            raise HTTPException(400,'Unknown template or format')
        if kind in ('roles_groups','opening_balances') and not u['is_superadmin']:
            from fastapi import HTTPException
            raise HTTPException(403,'Super Admin required for this template')
        if kind=='procedures':
            with db() as c:
                pricing=rows(c,'SELECT name FROM pricing_categories WHERE entity_id=? AND active=1 ORDER BY id',(eid,))
            names=[x['name'] for x in pricing]
            headers=['Procedure Name','Treatment Category',*names]
            sample=['Root Canal Treatment','Endodontics',*(['6000.00']*len(names))]
        else:
            headers=COMMON[kind]
            sample=EXAMPLES[kind]
        filename=f'rajan_dental_{kind}_sample.{format}'
        if format=='csv':
            output=StringIO()
            w=csv.writer(output)
            w.writerow(headers)
            w.writerow(sample)
            data=output.getvalue().encode('utf-8-sig')
            mime='text/csv'
        else:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
            from openpyxl.utils import get_column_letter
            wb=Workbook()
            ws=wb.active
            ws.title='Import Data'
            ws.append(headers)
            ws.append(sample)
            for cell in ws[1]:
                cell.font=Font(bold=True,color='FFFFFF')
                cell.fill=PatternFill(fill_type='solid',fgColor='D54F1A')
                cell.alignment=Alignment(wrap_text=True)
            for i,h in enumerate(headers,1):
                ws.column_dimensions[get_column_letter(i)].width=min(42,max(19,len(h)+3))
            ws.freeze_panes='A2'
            help_sheet=wb.create_sheet('Instructions')
            for line in TEMPLATE_NOTES:help_sheet.append([line])
            help_sheet.column_dimensions['A'].width=105
            output=BytesIO()
            wb.save(output)
            data=output.getvalue()
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return StreamingResponse(BytesIO(data),media_type=mime,headers={'Content-Disposition':f'attachment; filename="{filename}"','Cache-Control':'no-store'})
