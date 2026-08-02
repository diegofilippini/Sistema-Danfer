from datetime import date, timedelta

from danfer_os.models.bom import BomComponent, BomCreate, BomStatus
from danfer_os.models.commercial import (
    ClientCreate,
    QuoteCreate,
    QuoteItemCreate,
    QuoteProcess,
    QuoteType,
)
from danfer_os.models.operations import (
    MaintenanceOrderCreate,
    MaintenanceType,
    QualityOccurrenceCreate,
    QualityType,
)
from danfer_os.models.pcp import ProductionOrderCreate
from danfer_os.models.technical_document import DocumentCategory, DocumentCreate
from danfer_os.services.bom import BomService
from danfer_os.services.commercial import CommercialService
from danfer_os.services.operations import OperationsService
from danfer_os.services.pcp import PcpService
from danfer_os.services.technical_library import TechnicalLibrary


def seed_demo(
    library: TechnicalLibrary,
    boms: BomService,
    pcp: PcpService,
    commercial: CommercialService,
    operations: OperationsService,
) -> None:
    if commercial.list_clients():
        return
    client = commercial.create_client(
        ClientCreate(
            name="Cliente Demonstração",
            document="00.000.000/0001-00",
            contact="Comprador Teste",
            email="compras@cliente-teste.com.br",
            phone="(54) 99999-0000",
            payment_terms="28/42 dias",
        )
    )
    existing_parts = {item.danfer_code: item for item in library.list()}
    product = existing_parts.get("DF-KIT-001") or library.create(
        DocumentCreate(
            danfer_code="DF-KIT-001",
            customer_code="KIT-DEMO",
            title="Conjunto suporte demonstrativo",
            customer=client.name,
            material="Aço carbono",
            thickness_mm=3,
            category=DocumentCategory.DRAWING,
            file_url="https://docs.danfer.com/DF-KIT-001.pdf",
        )
    )
    component = existing_parts.get("DF-CHAPA-001") or library.create(
        DocumentCreate(
            danfer_code="DF-CHAPA-001",
            title="Chapa base cortada e dobrada",
            material="Aço carbono",
            thickness_mm=3,
            weight_kg=4.8,
            category=DocumentCategory.DRAWING,
            file_url="https://docs.danfer.com/DF-CHAPA-001.pdf",
        )
    )
    bom = boms.create(
        BomCreate(
            product_id=product.id,
            revision="A",
            status=BomStatus.ACTIVE,
            components=[BomComponent(part_id=component.id, quantity=2)],
        )
    )
    commercial.create_quote(
        QuoteCreate(
            type=QuoteType.SALE,
            client_id=client.id,
            requester=client.contact,
            valid_until=date.today() + timedelta(days=10),
            expected_delivery=date.today() + timedelta(days=20),
            payment_terms=client.payment_terms,
            margin_percent=28,
            ipi_percent=5,
            items=[
                QuoteItemCreate(
                    code=product.danfer_code,
                    description=product.title,
                    quantity=10,
                    material="Aço carbono",
                    thickness_mm=3,
                    net_weight_kg=9.6,
                    material_price_kg=6.2,
                    utilization_percent=82,
                    processes=[
                        QuoteProcess(name="Corte laser", minutes=12, hourly_rate=180),
                        QuoteProcess(name="Dobra", minutes=8, hourly_rate=120),
                    ],
                )
            ],
            observations="Proposta demonstrativa para validação do sistema.",
        )
    )
    pcp.create(
        ProductionOrderCreate(
            product_id=product.id,
            bom_id=bom.id,
            quantity=5,
            due_date=date.today() + timedelta(days=7),
            priority=2,
            notes="Ordem demonstrativa",
        )
    )
    operations.create_quality(
        QualityOccurrenceCreate(
            type=QualityType.REWORK,
            production_order="OP-DEMO",
            description="Ocorrência demonstrativa para avaliação do módulo",
            responsible="Qualidade",
            cost=75,
        )
    )
    operations.create_maintenance(
        MaintenanceOrderCreate(
            equipment="Laser 01",
            type=MaintenanceType.PREVENTIVE,
            description="Revisão preventiva demonstrativa",
            scheduled_date=date.today() + timedelta(days=5),
            responsible="Manutenção",
        )
    )
